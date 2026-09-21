"""Tracing the query path with OpenTelemetry, into the usage database.

When an answer is bad, the question worth asking is which step went wrong:
retrieval returned nothing, the reranker buried the right passage, or the
model ignored what it was given. Each of those steps opens a span — the
agent's run, every model call, every tool call, and inside a search the
embedding, the lexical and vector searches, fusion, and reranking — and a
question's spans together are its trace.

Where spans go
==============

By default, into the usage database: the local, uncommitted file that already
holds the graph checkpoints and the captured records, in tables described in
:mod:`corpus_query.store.spans`. A trace is rows to query, not a service to
run. Two more destinations can be added, each by one environment variable:

- :data:`CONSOLE_VARIABLE` set to ``1`` (or ``true``) also prints every span
  to standard output as it ends.
- ``OTEL_EXPORTER_OTLP_ENDPOINT`` — the standard OpenTelemetry variable, or
  its traces-only form ``OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`` — also sends
  spans over OTLP/gRPC to whatever collector or backend is listening there.
  The exporter reads the rest of the standard ``OTEL_EXPORTER_OTLP_*``
  settings itself.

``OTEL_SDK_DISABLED=true``, the standard switch, turns tracing off: nothing
is recorded anywhere, and every span the code opens is a no-op.

Model spans follow the OpenTelemetry semantic conventions for generative AI —
``gen_ai.operation.name``, ``gen_ai.provider.name``, the requested and
responding model, token counts — so an OTLP backend that understands them
renders them without configuration. Everything this project adds is under
``corpus_query.``.

Why spans are written from a thread, and never from the event loop
==================================================================

The usage database is also where the graph checkpointer writes, and the
checkpointer issues the commit that ends each of its writes from the event
loop. Anything that blocked the loop while waiting for the file would wait on
a commit that cannot be issued until it stops waiting, and fail as locked.
So finished spans are handed to OpenTelemetry's batching processor, whose
worker thread writes them in batches over a connection it opens for each
batch. The event loop only ever appends to an in-memory queue.

Why the tracer provider is installed once and its destinations change
====================================================================

Instrumented code asks OpenTelemetry's global API for its tracer, which is
the convention: code that emits spans does not decide where they go. The
global provider can only be set once per process, though, and an application
opened twice in one process — which the test suite does constantly — may
want its spans in two different files. So the provider is installed once,
with one processor that forwards to whatever destinations are open, and
:func:`open_tracing` adds destinations to it and :meth:`Tracing.close` takes
them away again.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from opentelemetry import context as otel_context
from opentelemetry import propagate, trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.sdk.trace.sampling import Decision, Sampler, SamplingResult
from opentelemetry.trace import (
    Span,
    SpanKind,
    Status,
    StatusCode,
    format_span_id,
    format_trace_id,
)

from corpus_query.store import spans as span_store
from corpus_query.store.usage import usage_database

#: What the service calls itself on every span, as ``service.name``.
SERVICE_NAME = "corpus-query"

#: The instrumentation scope every span here is opened under.
SCOPE = "corpus_query"

#: Set to ``1`` or ``true`` to print spans to standard output as well.
CONSOLE_VARIABLE = "CORPUS_QUERY_TRACE_CONSOLE"

#: Either of these, set, sends spans over OTLP as well. Both are the
#: standard OpenTelemetry names, so the exporter reads them itself.
OTLP_VARIABLES = ("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "OTEL_EXPORTER_OTLP_ENDPOINT")

#: The standard OpenTelemetry switch. ``true`` turns tracing off.
DISABLED_VARIABLE = "OTEL_SDK_DISABLED"

# Attribute names from the OpenTelemetry semantic conventions for generative
# AI, checked against the conventions' repository
# (open-telemetry/semantic-conventions-genai, docs/gen-ai/gen-ai-spans.md and
# gen-ai-agent-spans.md). They are still marked as in development there, and
# the SDK's own constants for them live in a private module, so they are
# spelled out here once rather than imported.
OPERATION = "gen_ai.operation.name"
PROVIDER = "gen_ai.provider.name"
REQUEST_MODEL = "gen_ai.request.model"
REQUEST_TEMPERATURE = "gen_ai.request.temperature"
RESPONSE_MODEL = "gen_ai.response.model"
FINISH_REASONS = "gen_ai.response.finish_reasons"
INPUT_TOKENS = "gen_ai.usage.input_tokens"
OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
CONVERSATION = "gen_ai.conversation.id"
AGENT_NAME = "gen_ai.agent.name"
TOOL_NAME = "gen_ai.tool.name"
TOOL_TYPE = "gen_ai.tool.type"
TOOL_DESCRIPTION = "gen_ai.tool.description"
TOOL_CALL_ID = "gen_ai.tool.call.id"
DATA_SOURCE = "gen_ai.data_source.id"
RETRIEVAL_TOP_K = "gen_ai.retrieval.top_k"
RETRIEVAL_QUERY = "gen_ai.retrieval.query.text"
EMBEDDING_DIMENSIONS = "gen_ai.embeddings.dimension.count"
ERROR_TYPE = "error.type"

#: What ``error.type`` says of an operation that was stopped rather than
#: failed: the client went away, or the process was shutting down.
CANCELLED = "cancelled"

#: How the conventions name the two providers :mod:`corpus_query.agent.model`
#: can build, keyed by what LangChain calls them. Bedrock has a well-known
#: value; Ollama does not, so its own name is used, as the conventions allow.
_PROVIDERS = {"amazon_bedrock": "aws.bedrock", "ollama": "ollama"}

logger = logging.getLogger(__name__)

#: The tracer everything here opens spans with. Asked of the global API when
#: this module is imported, which hands back a proxy that starts recording
#: once :func:`open_tracing` has installed a provider, and is a no-op until
#: then — so code that runs with tracing never opened pays next to nothing.
tracer = trace.get_tracer(SCOPE)


class UsageDatabaseExporter(SpanExporter):
    """Writes finished spans to the usage database.

    Called by the batching processor on its worker thread, never on the event
    loop. A connection is opened for each batch and closed after it, since a
    SQLite connection belongs to the thread that opened it and a batch is
    infrequent enough that holding one open would buy nothing.
    """

    def __init__(self, database: Path) -> None:
        """Remember where to write.

        Args:
            database: The usage database, already resolved.
        """
        self.database = database

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        """Write one batch.

        Args:
            spans: The spans that have ended since the last batch.

        Returns:
            Whether they were written. A failure is logged rather than
            raised: losing a batch of spans must never fail a question.
        """
        try:
            connection = span_store.connect(self.database)
            try:
                span_store.write(connection, [span_row(span) for span in spans])
            finally:
                connection.close()
        except Exception:
            logger.exception("could not write spans to %s", self.database)
            return SpanExportResult.FAILURE
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        """Nothing is held open between batches, so nothing to release."""

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        """Every batch is written as it arrives, so there is nothing to flush."""
        return True


def span_row(span: ReadableSpan) -> span_store.SpanRow:
    """Turn a finished span into the row it is stored as.

    Args:
        span: A span that has ended.

    Returns:
        The row.
    """
    context = span.get_span_context()
    return span_store.SpanRow(
        trace_id=format_trace_id(context.trace_id),
        span_id=format_span_id(context.span_id),
        parent_span_id=(
            format_span_id(span.parent.span_id) if span.parent is not None else None
        ),
        name=span.name,
        kind=span.kind.name,
        start_time_unix_nano=span.start_time or 0,
        end_time_unix_nano=span.end_time or 0,
        status_code=span.status.status_code.name,
        status_message=span.status.description,
        attributes=_plain(span.attributes),
        events=[
            {
                "name": event.name,
                "time_unix_nano": event.timestamp,
                "attributes": _plain(event.attributes),
            }
            for event in span.events
        ],
        scope=span.instrumentation_scope.name if span.instrumentation_scope else "",
    )


def _plain(attributes: Mapping[str, Any] | None) -> dict[str, Any]:
    """Copy span attributes into plain JSON-ready values.

    The SDK stores sequences as tuples, which JSON has no word for.
    """
    return {
        key: list(value) if isinstance(value, tuple) else value
        for key, value in (attributes or {}).items()
    }


class _Destinations(SpanProcessor):
    """The one processor the global provider has, forwarding to the rest.

    See the module docstring for why destinations are added and removed here
    rather than on the provider itself.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._processors: tuple[SpanProcessor, ...] = ()

    def add(self, processor: SpanProcessor) -> None:
        """Start forwarding to a processor."""
        with self._lock:
            self._processors = (*self._processors, processor)

    def remove(self, processor: SpanProcessor) -> None:
        """Stop forwarding to a processor."""
        with self._lock:
            self._processors = tuple(p for p in self._processors if p is not processor)

    def on_start(self, span: Any, parent_context: Any = None) -> None:
        """Forward a span that has started."""
        for processor in self._processors:
            processor.on_start(span, parent_context=parent_context)

    def on_end(self, span: ReadableSpan) -> None:
        """Forward a span that has ended."""
        for processor in self._processors:
            processor.on_end(span)

    @property
    def open(self) -> bool:
        """Whether anything is listening."""
        return bool(self._processors)

    def shutdown(self) -> None:
        """Leave each destination to whoever opened it."""

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        """Flush every open destination."""
        return all(p.force_flush(timeout_millis) for p in self._processors)


class _WhileOpen(Sampler):
    """Records spans while a destination is open, and none otherwise.

    Once the provider is installed it stays installed, so without this a
    process that closed its tracing — or opened it with tracing off after an
    earlier application had it on — would go on building spans nobody
    receives, each with a trace id that leads nowhere. A span this drops is
    a no-op with no trace id; see :func:`trace_id`.
    """

    def should_sample(
        self,
        parent_context: Any,
        trace_id: int,
        name: str,
        kind: Any = None,
        attributes: Any = None,
        links: Any = None,
        trace_state: Any = None,
    ) -> SamplingResult:
        """Record and sample while anything is listening, drop otherwise."""
        if not _DESTINATIONS.open:
            return SamplingResult(Decision.DROP)
        parent = trace.get_current_span(parent_context).get_span_context()
        return SamplingResult(
            Decision.RECORD_AND_SAMPLE,
            attributes,
            parent.trace_state if parent.is_valid else None,
        )

    def get_description(self) -> str:
        """Name the sampler, as the SDK reports it."""
        return "WhileOpen"


_DESTINATIONS = _Destinations()
_install_lock = threading.Lock()
_installed = False


def _install() -> None:
    """Put the forwarding processor on the global tracer provider, once.

    If something else in the process already configured an SDK provider,
    the processor is added to that one rather than fighting over the global.
    """
    global _installed
    with _install_lock:
        if _installed:
            return
        current = trace.get_tracer_provider()
        if isinstance(current, TracerProvider):
            current.add_span_processor(_DESTINATIONS)
        else:
            provider = TracerProvider(
                resource=Resource.create({"service.name": SERVICE_NAME}),
                sampler=_WhileOpen(),
            )
            provider.add_span_processor(_DESTINATIONS)
            trace.set_tracer_provider(provider)
        _installed = True


@dataclass
class Tracing:
    """Where one application's spans are going, until it is closed."""

    enabled: bool
    """False when tracing was turned off; nothing is recorded then."""

    database: Path | None = None
    """The usage database spans are written to, or None when off."""

    exporters: list[SpanExporter] = field(default_factory=list)
    """Every destination, the usage database's first."""

    processors: list[SpanProcessor] = field(default_factory=list)

    def flush(self) -> bool:
        """Write every span that has ended so far, and wait for it.

        Blocks the calling thread while the batch is written, so it is not
        for the event loop; see :meth:`aclose`.

        Returns:
            Whether every destination finished.
        """
        return all(processor.force_flush() for processor in self.processors)

    def close(self) -> None:
        """Stop sending spans here, after writing what is still queued."""
        for processor in self.processors:
            _DESTINATIONS.remove(processor)
            processor.shutdown()
        self.processors = []

    async def aclose(self) -> None:
        """Close, from the event loop, without blocking it."""
        await asyncio.to_thread(self.close)

    def __enter__(self) -> Tracing:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def open_tracing(
    database: Path | str | None = None,
    env: Mapping[str, str] | None = None,
) -> Tracing:
    """Start recording spans, into the usage database and wherever else asked.

    Args:
        database: The usage database to write spans to. None resolves to the
            project's default now, when tracing is opened.
        env: Settings to read the switches from. The process environment
            when not given.

    Returns:
        What is recording, to close when the application stops.

    Raises:
        SpansSchemaVersionError: If the usage database holds span tables at
            a version this code does not know. Checked here, at startup,
            rather than left to the first batch, which would log the failure
            on a background thread and drop every span after it.
    """
    settings = os.environ if env is None else env
    if settings.get(DISABLED_VARIABLE, "").strip().lower() == "true":
        return Tracing(enabled=False)
    resolved = usage_database(database)
    span_store.connect(resolved).close()
    _install()
    exporters: list[SpanExporter] = [UsageDatabaseExporter(resolved)]
    processors: list[SpanProcessor] = [BatchSpanProcessor(exporters[0])]
    if settings.get(CONSOLE_VARIABLE, "").strip().lower() in ("1", "true", "yes"):
        # Standard output as it is now, not as it was when the SDK was
        # imported, which is what the exporter would default to.
        console = ConsoleSpanExporter(service_name=SERVICE_NAME, out=sys.stdout)
        exporters.append(console)
        # Printed as each span ends, which is what watching a run wants.
        processors.append(SimpleSpanProcessor(console))
    if any(settings.get(name, "").strip() for name in OTLP_VARIABLES):
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )

        otlp = OTLPSpanExporter()
        exporters.append(otlp)
        processors.append(BatchSpanProcessor(otlp))
    for processor in processors:
        _DESTINATIONS.add(processor)
    return Tracing(
        enabled=True, database=resolved, exporters=exporters, processors=processors
    )


@contextmanager
def span(
    name: str,
    attributes: Mapping[str, Any] | None = None,
    kind: SpanKind = SpanKind.INTERNAL,
) -> Iterator[Span]:
    """Open a span around a block, as the current span.

    An exception out of the block ends the span as failed, with
    ``error.type`` saying what kind of failure; see :func:`failed`.

    Args:
        name: The span's name.
        attributes: What is known when it starts. None values are dropped.
        kind: The span kind.

    Yields:
        The span, to add what is learned along the way.
    """
    with tracer.start_as_current_span(
        name,
        kind=kind,
        attributes=_settable(attributes),
        record_exception=False,
        set_status_on_exception=False,
    ) as current:
        try:
            yield current
        except BaseException as exc:
            failed(current, exc)
            raise


def failed(current: Span, exc: BaseException) -> None:
    """Mark a span as having ended in failure.

    Cancellation is reported as ``cancelled`` rather than as the exception
    that carried it: a client that went away is not a fault in the step it
    interrupted, but a span that ended without its work being done should
    not read as a success either.

    Args:
        current: The span.
        exc: What ended it.
    """
    if isinstance(exc, asyncio.CancelledError | GeneratorExit):
        current.set_attribute(ERROR_TYPE, CANCELLED)
        current.set_status(Status(StatusCode.ERROR, "cancelled before it finished"))
        return
    kind = type(exc)
    qualified = (
        kind.__qualname__
        if kind.__module__ == "builtins"
        else f"{kind.__module__}.{kind.__qualname__}"
    )
    current.set_attribute(ERROR_TYPE, qualified)
    current.record_exception(exc)
    current.set_status(Status(StatusCode.ERROR, f"{kind.__name__}: {exc}"))


def annotate(current: Span, attributes: Mapping[str, Any]) -> None:
    """Add attributes to a span, dropping any that are None.

    Args:
        current: The span.
        attributes: What to add.
    """
    current.set_attributes(_settable(attributes))


def _settable(attributes: Mapping[str, Any] | None) -> dict[str, Any]:
    """Drop None values and turn lists into tuples, which a span accepts."""
    return {
        key: tuple(value) if isinstance(value, list) else value
        for key, value in (attributes or {}).items()
        if value is not None
    }


@contextmanager
def attached(parent: otel_context.Context) -> Iterator[None]:
    """Make a context current for the length of a block.

    For code that has to hand a span to work it starts without being inside
    a ``with`` for the span's whole life — the agent's run, which is an
    async generator whose consumer resumes it from wherever it likes.
    Attaching and detaching within one block keeps both in the same
    context, which is what :mod:`contextvars` requires.

    Args:
        parent: The context to make current.

    Yields:
        Nothing.
    """
    token = otel_context.attach(parent)
    try:
        yield
    finally:
        otel_context.detach(token)


def trace_id(current: Span) -> str:
    """Return a span's trace id as 32 hex digits, or "" when it went nowhere.

    Args:
        current: A span, possibly a no-op one.

    Returns:
        The id, as the usage database stores it, for a span that was
        sampled. An empty string when tracing is off, since an id for a
        trace that was never written would send whoever follows it looking
        for nothing.
    """
    context = current.get_span_context()
    if not (context.is_valid and context.trace_flags.sampled):
        return ""
    return format_trace_id(context.trace_id)


def headers() -> dict[str, str]:
    """Return the headers that carry the current trace to another service.

    W3C trace context, which is OpenTelemetry's default propagator. Empty
    when there is no current span.
    """
    carrier: dict[str, str] = {}
    propagate.inject(carrier)
    return carrier


@contextmanager
def continued(carrier: Mapping[str, str]) -> Iterator[None]:
    """Continue the trace a request's headers carry, if they carry one.

    A request without trace context leaves the current context alone,
    rather than replacing it with an empty one — in process, the caller's
    span is already current.

    Args:
        carrier: The request's headers.

    Yields:
        Nothing.
    """
    if "traceparent" not in carrier:
        yield
        return
    with attached(propagate.extract(carrier)):
        yield


@dataclass(frozen=True)
class ModelIdentity:
    """What a chat model is, in the conventions' terms."""

    provider: str
    """``gen_ai.provider.name``."""

    model: str | None
    """``gen_ai.request.model``, when the model says."""

    temperature: float | None = None
    """``gen_ai.request.temperature``, when the model says."""

    @property
    def span_name(self) -> str:
        """``chat {model}``, as the conventions name an inference span."""
        return f"chat {self.model}" if self.model else "chat"


def identify(model: Any) -> ModelIdentity:
    """Say which provider and model a LangChain chat model is.

    Read from the parameters LangChain reports for its own tracing, which
    both of this project's backends provide. A model that does not — the
    scripted one the tests answer with — is reported as ``unknown``.

    Args:
        model: The chat model, before any tools are bound to it.

    Returns:
        Its identity.
    """
    try:
        params = model._get_ls_params()
    except Exception:
        params = {}
    provider = str(params.get("ls_provider") or "unknown")
    temperature = params.get("ls_temperature")
    return ModelIdentity(
        provider=_PROVIDERS.get(provider, provider),
        model=params.get("ls_model_name") or None,
        temperature=float(temperature) if temperature is not None else None,
    )


def response_attributes(reply: Any) -> dict[str, Any]:
    """Read what a model's reply says about itself, as span attributes.

    Args:
        reply: The message the model returned.

    Returns:
        The responding model, why it stopped, and the tokens it used, where
        the reply carries them. Ollama and Bedrock put these in different
        places, and both are read. Bedrock's client also retries some
        failures inside a single call; how many times is recorded, since
        those retries happen below anything this code can open a span
        around.
    """
    metadata = getattr(reply, "response_metadata", None) or {}
    usage = getattr(reply, "usage_metadata", None) or {}
    reason = (
        metadata.get("done_reason")
        or metadata.get("stopReason")
        or metadata.get("stop_reason")
    )
    retries = (metadata.get("ResponseMetadata") or {}).get("RetryAttempts")
    return {
        RESPONSE_MODEL: metadata.get("model_name") or metadata.get("model"),
        FINISH_REASONS: [str(reason)] if reason else None,
        INPUT_TOKENS: usage.get("input_tokens"),
        OUTPUT_TOKENS: usage.get("output_tokens"),
        "corpus_query.model.client_retries": retries,
    }


async def call_model(
    speaker: Any,
    messages: list[Any],
    identity: ModelIdentity,
    step: str,
    conversation: str | None = None,
) -> Any:
    """Call a chat model inside an inference span.

    One span per call. Anything that calls again after a failure — a retry
    policy on a graph node, a caller trying twice — goes through here again
    and gets a span of its own beside the first, rather than being folded
    into the span of the attempt that succeeded.

    Args:
        speaker: What to call: the model, or the model with tools bound.
        messages: The prompt.
        identity: What the model is; see :func:`identify`.
        step: Which step of the graph is calling, as
            ``corpus_query.agent.step``.
        conversation: The thread the call belongs to.

    Returns:
        The model's reply.
    """
    with span(
        identity.span_name,
        {
            OPERATION: "chat",
            PROVIDER: identity.provider,
            REQUEST_MODEL: identity.model,
            REQUEST_TEMPERATURE: identity.temperature,
            CONVERSATION: conversation,
            "corpus_query.agent.step": step,
        },
        kind=SpanKind.CLIENT,
    ) as current:
        reply = await speaker.ainvoke(messages)
        annotate(current, response_attributes(reply))
        return reply


def confidence_attributes(confidence: Mapping[str, Any] | None) -> dict[str, Any]:
    """Carry a search's confidence signals onto a span, as they were reported.

    Nothing is recomputed: these are the numbers the search response
    already carries, under names of their own.

    Args:
        confidence: The response's ``confidence`` object.

    Returns:
        The attributes. Signals the search did not report are left out.
    """
    confidence = confidence or {}
    return {
        "corpus_query.confidence.top_score": confidence.get("top_score"),
        "corpus_query.confidence.margin": confidence.get("margin"),
        "corpus_query.confidence.lexical_dense_agree": confidence.get(
            "lexical_dense_agree"
        ),
        "corpus_query.confidence.unmatched_terms": list(
            confidence.get("unmatched_terms") or []
        ),
    }
