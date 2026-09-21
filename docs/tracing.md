# Tracing each query

When an answer is bad, the useful question is which step went wrong: retrieval
found nothing, the reranker buried the right passage, or the model ignored what
it was given. Every `/search` and `/answer` is traced with
[OpenTelemetry](https://opentelemetry.io/) so that is something to look up
rather than guess at. An answer's trace holds a span for the run, one for each
model call (the rewrite, each draft, verification, routing), one for each
search the model asked for, and under each search one for embedding the query,
the lexical search, the vector search, fusion, and reranking.

The spans carry the numbers that explain them. A search's span lists the
passages it returned with their rerank scores and where lexical search, vector
search, and fusion had each put them beforehand, alongside the confidence
signals `/search` already reports. A model call's span follows the
[semantic conventions for generative
AI](https://github.com/open-telemetry/semantic-conventions-genai) — provider,
model, token counts, why it stopped — so a tracing backend that knows them
shows them without configuration.

Spans are written to the `spans` table in `data/usage.db`, a few seconds after
they end, so reading a trace is a query:

```bash
sqlite3 data/usage.db "
  SELECT name,
         (end_time_unix_nano - start_time_unix_nano) / 1e6 AS ms,
         json_extract(attributes, '$.\"gen_ai.usage.output_tokens\"') AS tokens
  FROM spans
  WHERE trace_id = (SELECT trace_id FROM spans ORDER BY start_time_unix_nano DESC LIMIT 1)
  ORDER BY start_time_unix_nano"
```

Three environment variables change where they go:

| Variable | Effect |
|---|---|
| `CORPUS_QUERY_TRACE_CONSOLE=1` | Also print each span to standard output as it ends. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Also send spans over OTLP/gRPC to the collector at that address, such as `http://localhost:4317`. The other standard `OTEL_EXPORTER_OTLP_*` settings apply. |
| `OTEL_SDK_DISABLED=true` | Turn tracing off. Nothing is recorded, and answering is otherwise unchanged. |

The last two are OpenTelemetry's own names, so they mean here what they mean
anywhere else.
