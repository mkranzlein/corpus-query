-- How each query was executed, as OpenTelemetry spans.
--
-- These tables live in the usage database, beside the graph checkpoints and
-- the captured records, and never in the committed corpus. One row per span:
-- a trace is the rows that share a trace_id, and parent_span_id is what puts
-- them back into a tree.

-- Which version of these tables the file holds. A row rather than the
-- database's user_version pragma, for the same reason capture_meta is one:
-- the file is shared, and a pragma that is one property of the whole file
-- cannot honestly describe one writer's tables in it. See the module
-- docstring of corpus_query.store.spans.
CREATE TABLE spans_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE spans (
    -- Hex, the way the W3C trace context header and every OTLP backend
    -- print them, so an id copied out of this table can be pasted into one.
    trace_id TEXT NOT NULL,
    span_id TEXT NOT NULL,
    -- Null for the span a trace starts from.
    parent_span_id TEXT,
    name TEXT NOT NULL,
    -- INTERNAL, CLIENT, SERVER, PRODUCER, or CONSUMER.
    kind TEXT NOT NULL,
    -- Nanoseconds since the Unix epoch, as the SDK records them. Integers
    -- rather than formatted text because durations are computed from them,
    -- and a formatted time would round away most of a fast span.
    start_time_unix_nano INTEGER NOT NULL,
    end_time_unix_nano INTEGER NOT NULL,
    -- UNSET, OK, or ERROR, and what went wrong when it is ERROR.
    status_code TEXT NOT NULL,
    status_message TEXT,
    -- The span's attributes as a JSON object. Stored whole rather than as
    -- rows: SQLite's JSON functions reach into it when a query needs one.
    attributes TEXT NOT NULL,
    -- What happened during the span, as a JSON array of name, time, and
    -- attributes. A recorded exception is one of these.
    events TEXT NOT NULL,
    -- Which instrumentation produced the span.
    scope TEXT NOT NULL,
    PRIMARY KEY (trace_id, span_id)
);

CREATE INDEX idx_spans_start ON spans (start_time_unix_nano);
