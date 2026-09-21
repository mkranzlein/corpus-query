# Answer metrics

A trace says what happened in one query. Noticing that answers have got worse
needs the other direction: the same few numbers for every query, cheap to read
across thousands of them. Those numbers are columns on the answer row in
`data/usage.db` — the row every question writes, abstentions included — so
reading a trend is one `GROUP BY` rather than a walk through span trees.

## What each row carries

| Column | Meaning |
|---|---|
| `abstained` | 1 when the turn searched and the record did not settle the question. |
| `searches` | How many searches the turn ran. 0 for a question declined as out of scope and for a correction typed into the conversation. |
| `top_score` | The best rerank score any of the turn's searches returned. |
| `margin` | The gap between the first and second result of that same search. |
| `citation_coverage` | The share of the answer's sentences the retrieved passages bear out, 0 to 1. Defined below. |
| `latency_ms` | Milliseconds from the question reaching the agent to the finished answer. |
| `backend`, `model` | What answered: `ollama` or `aws.bedrock`, as OpenTelemetry names the provider, and the model as that provider names it. |
| `trace_id` | The trace the answer's spans were recorded under. `spans.trace_id` is the other end. Null when tracing was off. |

A number the turn had nothing to compute from is null, not zero: no search
means no `top_score`, and no passage means no `citation_coverage`. Rows written
before these columns existed are kept, with every one of them null.

### Citation coverage

Computed from text alone, with no model call, so it costs nothing per query
and does not move when the model that answers changes:

1. Split the answer into sentences at `.`, `!`, or `?` followed by whitespace.
2. Reduce each sentence to its content words: lowercased runs of letters and
   digits, less a short list of English function words ("the", "was", "of").
   A sentence with none left is not counted.
3. A sentence is supported when at least half of its distinct content words
   appear in **one** passage the turn retrieved — its source line and its
   text, reduced the same way.
4. Coverage is supported sentences over counted sentences.

It is lexical. A faithful paraphrase counts as unsupported, and a sentence
that reuses a passage's words to claim something the passage does not say
counts as supported. It is for seeing a shift across many answers, not for
grading one. The code is `corpus_query/agent/measures.py`.

## Reading it

Each of these is tested against the schema, so they stay correct as it
changes. `searches > 0` keeps to the turns that consulted the record, which
is where abstaining and citing mean anything, and leaves out rows from before
these columns existed.

```sql
-- abstention rate by day
SELECT date(created_at) AS day,
       count(*) AS answers,
       avg(abstained) AS abstention_rate
FROM answers
WHERE searches > 0
GROUP BY day
ORDER BY day;
```

```sql
-- citation coverage by day
SELECT date(created_at) AS day,
       count(*) AS answers,
       avg(citation_coverage) AS citation_coverage
FROM answers
WHERE searches > 0 AND abstained = 0 AND citation_coverage IS NOT NULL
GROUP BY day
ORDER BY day;
```

A correction arrives after the answer it corrects, so it is a row of its own
pointing at the answer rather than a column that changes later. The rate is
still a query over answers: each one either has a correction or it does not,
counted on the day the answer was given.

```sql
-- correction rate by day
SELECT date(a.created_at) AS day,
       count(*) AS answers,
       avg(EXISTS (SELECT 1 FROM corrections AS c WHERE c.answer_id = a.id))
           AS correction_rate
FROM answers AS a
WHERE a.searches > 0
GROUP BY day
ORDER BY day;
```

When a day looks wrong, the trace id goes from the number to the executions
behind it:

```sql
-- the spans behind the least supported answers
SELECT a.query, a.citation_coverage, s.name,
       (s.end_time_unix_nano - s.start_time_unix_nano) / 1e6 AS ms
FROM answers AS a
JOIN spans AS s ON s.trace_id = a.trace_id
WHERE a.citation_coverage IS NOT NULL
ORDER BY a.citation_coverage, a.id, s.start_time_unix_nano
LIMIT 50;
```

## What this does and does not detect

These are production metrics. They are measured on whatever people happened to
ask, and there is no golden set of questions with known answers behind them.
That has two consequences.

- **They detect movement, not correctness.** A falling coverage or a rising
  abstention rate says something changed. None of these numbers says an
  individual answer was right.
- **A change in what people ask cannot be told apart from a regression.** A
  week of questions the corpus never covered raises the abstention rate
  exactly as broken retrieval would. The numbers can show the shift; deciding
  which it was means reading the answers, starting from the trace ids.

Two smoke queries in the test suite (`tests/test_smoke_queries.py`) pin the
behavior most worth not losing: a question the corpus answers must come back
with citations, and one it does not must abstain and suggest who to ask. They
run against the committed corpus with real retrieval when the models are
installed, and against stubbed retrieval otherwise. The model in them is
scripted, so they check what the system does with a model's decisions, not
the decisions themselves.

Not built: dashboards or alerts over these numbers, a golden evaluation set,
and scoring every trace with a model or a hosted evaluation platform. The last
is the natural next step when lexical coverage stops being enough.
