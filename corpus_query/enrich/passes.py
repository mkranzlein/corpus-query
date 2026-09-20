"""The model calls, one function per pass.

Every pass has the same shape: assemble a prompt from a committed template,
ask for a structured response, and hand back something already validated.
Nothing here touches the store — a pass that has produced a summary has not
yet written one — so the caller can put a whole document's enrichment into
one transaction.

A response that does not validate, or that carries no parsed output at all,
raises :class:`~corpus_query.enrich.errors.EnrichmentError`. That is what
lets a corpus run report one bad document and carry on with the rest.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from corpus_query.enrich import prompts
from corpus_query.enrich.documents import StoredDocument, describe
from corpus_query.enrich.errors import EnrichmentError
from corpus_query.enrich.schema import (
    BUSINESS_IMPACT_VALUES,
    MAX_SUMMARY_SENTENCES,
    MAX_TOPICS,
    MIN_SUMMARY_SENTENCES,
    TIME_SENSITIVITY_VALUES,
    DocumentSummary,
    PriorityAssessment,
    TopicAssignment,
    TopicMerge,
    TopicMerges,
)
from corpus_query.enrich.topics import describe_categories

#: Low, because none of these passes wants invention. A summary and a
#: category assignment should come out the same way twice; this is the
#: opposite of the generator, whose whole job is variety.
TEMPERATURE = 0.2

_Parsed = TypeVar("_Parsed", bound=BaseModel)


def summary_prompt(document: StoredDocument) -> str:
    """Assemble the summary prompt for one document.

    Args:
        document: The document to summarize.

    Returns:
        The prompt, ready to send.

    Raises:
        PromptError: If the template cannot be read or filled.
    """
    return prompts.render(
        "summary",
        {
            "document": describe(document),
            "min_sentences": str(MIN_SUMMARY_SENTENCES),
            "max_sentences": str(MAX_SUMMARY_SENTENCES),
        },
    )


def topics_prompt(document: StoredDocument, categories: Sequence[str]) -> str:
    """Assemble the topic prompt for one document.

    Args:
        document: The document to file.
        categories: Every category that exists right now, including the ones
            earlier documents in this run created.

    Returns:
        The prompt, ready to send.

    Raises:
        PromptError: If the template cannot be read or filled.
    """
    return prompts.render(
        "topics",
        {
            "document": describe(document),
            "categories": describe_categories(categories),
            "max_topics": str(MAX_TOPICS),
        },
    )


def priority_prompt(document: StoredDocument) -> str:
    """Assemble the priority prompt for one document.

    Args:
        document: The document to assess.

    Returns:
        The prompt, ready to send.

    Raises:
        PromptError: If the template cannot be read or filled.
    """
    return prompts.render(
        "priority",
        {
            "document": describe(document),
            "time_sensitivity": _bullets(TIME_SENSITIVITY_VALUES),
            "business_impact": _bullets(BUSINESS_IMPACT_VALUES),
        },
    )


def dedupe_prompt(categories: Sequence[str]) -> str:
    """Assemble the dedupe prompt for the finished category list.

    Args:
        categories: Every category in the store.

    Returns:
        The prompt, ready to send.

    Raises:
        PromptError: If the template cannot be read or filled.
    """
    return prompts.render("dedupe", {"categories": describe_categories(categories)})


def summarize(client: Any, model: str, document: StoredDocument) -> str:
    """Ask for a document's summary.

    Args:
        client: An OpenAI-compatible client.
        model: The model id to call.
        document: The document to summarize.

    Returns:
        The summary, normalized onto one paragraph.

    Raises:
        EnrichmentError: If the response is missing or does not validate.
    """
    parsed = request(client, model, summary_prompt(document), DocumentSummary)
    return parsed.summary


def choose_topics(
    client: Any, model: str, document: StoredDocument, categories: Sequence[str]
) -> list[str]:
    """Ask which categories a document belongs under.

    Args:
        client: An OpenAI-compatible client.
        model: The model id to call.
        document: The document to file.
        categories: Every category that exists right now.

    Returns:
        The chosen category names, at most :data:`MAX_TOPICS` of them. A name
        that is not in ``categories`` is a new category the pass is asking
        for; creating it is the store's business, not this function's.

    Raises:
        EnrichmentError: If the response is missing or does not validate.
    """
    parsed = request(
        client, model, topics_prompt(document, categories), TopicAssignment
    )
    return parsed.topics


def assess_priority(
    client: Any, model: str, document: StoredDocument
) -> PriorityAssessment:
    """Ask how time sensitive a document is, and how much it moves.

    Args:
        client: An OpenAI-compatible client.
        model: The model id to call.
        document: The document to assess.

    Returns:
        Both fields, each already checked against its vocabulary.

    Raises:
        EnrichmentError: If the response is missing, or names a value
            outside either vocabulary.
    """
    return request(client, model, priority_prompt(document), PriorityAssessment)


def propose_merges(
    client: Any, model: str, categories: Sequence[str]
) -> list[TopicMerge]:
    """Ask which categories mean the same thing.

    Args:
        client: An OpenAI-compatible client.
        model: The model id to call.
        categories: Every category in the store.

    Returns:
        One group per set of duplicates. Empty when the list is already
        clean, which is a normal answer rather than a failure.

    Raises:
        EnrichmentError: If the response is missing or does not validate.
    """
    parsed = request(client, model, dedupe_prompt(categories), TopicMerges)
    return parsed.merges


def request(
    client: Any, model: str, prompt: str, text_format: type[_Parsed]
) -> _Parsed:
    """Send one prompt and validate what comes back.

    Args:
        client: An OpenAI-compatible client.
        model: The model id to call.
        prompt: The assembled prompt.
        text_format: The shape the response has to take.

    Returns:
        The parsed, validated response.

    Raises:
        EnrichmentError: If the response carried no parsed structured
            output, or carried one that does not validate.
    """
    try:
        response = client.responses.parse(
            model=model,
            input=prompt,
            text_format=text_format,
            temperature=TEMPERATURE,
        )
    except ValidationError as exc:
        raise EnrichmentError(
            f"The {text_format.__name__} response did not validate: {exc}"
        ) from exc
    parsed = response.output_parsed
    if parsed is None:
        raise EnrichmentError(
            f"The {text_format.__name__} response carried no parsed structured output."
        )
    return parsed


def _bullets(values: Sequence[str]) -> str:
    """Render a vocabulary as a bulleted list for a prompt.

    Args:
        values: The permitted values, in order.

    Returns:
        One bullet per value. Written from the vocabulary itself so the
        prompt cannot drift from what validation will accept.
    """
    return "\n".join(f"- `{value}`" for value in values)
