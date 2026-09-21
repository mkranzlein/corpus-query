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
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX idx_answers_created_at ON answers (created_at);
CREATE INDEX idx_answers_thread_id ON answers (thread_id);

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
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX idx_feedback_created_at ON feedback (created_at);
CREATE INDEX idx_feedback_answer_id ON feedback (answer_id);
