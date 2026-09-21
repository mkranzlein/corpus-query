-- The captured record of the system being used.
--
-- These tables live in the usage database, beside the graph checkpoints, and
-- never in the committed corpus. Asking a question writes here; it does not
-- touch a file that is under version control.
--
-- Four tables, and the first one is the spine. Every question answered
-- writes one answer row, and a gap, a correction, or a piece of feedback is
-- a row pointing at it. That is what lets a correction written a week later
-- name the answer it corrects rather than a question string that may have
-- been asked twice.

-- Which version of these tables the file holds. A row rather than the
-- database's user_version pragma, because this file is shared: LangGraph's
-- checkpointer creates its own tables here and does not set user_version, so
-- a pragma that is one property of the whole file cannot honestly describe
-- one library's tables in it. See the module docstring.
CREATE TABLE capture_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- One row per question answered: the one record per query in the system.
--
-- Anything later that wants per-query numbers adds columns here rather than
-- a second table recording the same event, so an id handed out here has to
-- stay the thing everything else points at.
CREATE TABLE answers (
    -- A generated hex id rather than a rowid. It is minted before the row is
    -- written and handed straight back to the caller, it is what a later
    -- correction names, and it says nothing about how many questions have
    -- been asked.
    id TEXT PRIMARY KEY,
    -- The conversation this answer belongs to, as the agent's thread store
    -- keys it. Not a foreign key: threads are LangGraph's tables, not ours.
    thread_id TEXT NOT NULL,
    query TEXT NOT NULL,
    answer TEXT NOT NULL,
    -- The passages the answer rests on, as the JSON array the API returns.
    -- Stored whole rather than as rows because nothing queries inside it:
    -- it is read back to show a reader what the answer was built from.
    citations TEXT NOT NULL,
    -- Whether the record failed to settle the question. An abstention is a
    -- measurement, not a missing row, so it is a column here and the row is
    -- written either way.
    abstained INTEGER NOT NULL CHECK (abstained IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    -- The per-query numbers, below, came with version 3. They are after
    -- created_at because that is where ALTER TABLE puts a column, and a file
    -- upgraded from version 2 and a file created at version 3 should have
    -- the same table. A row written before version 3 has them all null,
    -- which reads as not measured rather than as zero. What each one means,
    -- and the SQL that reads them, is in docs/answer-metrics.md.
    --
    -- How many searches the turn ran. Zero for a question declined as out
    -- of scope and for a correction typed into the conversation, which is
    -- what lets a rate be taken over the turns that consulted the record.
    searches INTEGER,
    -- The best rerank score any of the turn's searches returned, and the gap
    -- between that search's first and second result. Null when nothing was
    -- searched or nothing came back.
    top_score REAL,
    margin REAL,
    -- The share of the answer's sentences whose content words are mostly
    -- found in one retrieved passage, from 0 to 1. Null when the turn
    -- retrieved no passage to check against.
    citation_coverage REAL,
    -- Wall-clock milliseconds from the question reaching the agent to the
    -- finished answer.
    latency_ms INTEGER,
    -- What answered: the provider as OpenTelemetry names it (ollama,
    -- aws.bedrock) and the model as that provider names it.
    backend TEXT,
    model TEXT,
    -- The trace the answer's spans were recorded under, as 32 hex digits,
    -- or null when tracing was off. spans.trace_id is the other end.
    trace_id TEXT
);

CREATE INDEX idx_answers_created_at ON answers (created_at);
CREATE INDEX idx_answers_thread_id ON answers (thread_id);
CREATE INDEX idx_answers_trace_id ON answers (trace_id);

-- A question the record did not settle. System-detected: written when the
-- agent abstains or routes, and nobody has to remember to file it.
CREATE TABLE gaps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    -- The question a gap is about is the one on the answer row, and it is
    -- not repeated here. A copy would be a second place for the same string
    -- to live, and the point of the answer row is that there is one.
    answer_id TEXT NOT NULL REFERENCES answers (id) ON DELETE CASCADE,
    -- Who to ask, as the JSON the response carries, or null when the
    -- passages named nobody on the roster and there was no one to suggest.
    routing TEXT,
    -- When someone reading the review queue marked this seen, or null while
    -- it is still new. A timestamp rather than a flag, because when an item
    -- was looked at is worth keeping and costs nothing more than whether.
    reviewed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX idx_gaps_created_at ON gaps (created_at);
CREATE INDEX idx_gaps_answer_id ON gaps (answer_id);

-- A user saying what was wrong and what is right. Recorded for people to
-- read; nothing applies it to a later answer.
CREATE TABLE corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    answer_id TEXT NOT NULL REFERENCES answers (id) ON DELETE CASCADE,
    what_was_wrong TEXT NOT NULL,
    what_is_right TEXT NOT NULL,
    -- When someone reading the review queue marked this seen, or null while
    -- it is still new. A timestamp rather than a flag, because when an item
    -- was looked at is worth keeping and costs nothing more than whether.
    reviewed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX idx_corrections_created_at ON corrections (created_at);
CREATE INDEX idx_corrections_answer_id ON corrections (answer_id);

-- A verdict on an answer, with an optional note. Deliberately not a
-- correction: a thumbs down asserts that an answer was bad and carries
-- nothing a reader can act on, and mixing the two would fill a queue of
-- things to act on with things nobody can.
CREATE TABLE feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    answer_id TEXT NOT NULL REFERENCES answers (id) ON DELETE CASCADE,
    verdict TEXT NOT NULL CHECK (verdict IN ('up', 'down')),
    note TEXT,
    -- When someone reading the review queue marked this seen, or null while
    -- it is still new. A timestamp rather than a flag, because when an item
    -- was looked at is worth keeping and costs nothing more than whether.
    reviewed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX idx_feedback_created_at ON feedback (created_at);
CREATE INDEX idx_feedback_answer_id ON feedback (answer_id);
