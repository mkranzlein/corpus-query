-- The document store schema.
--
-- One SQLite file is the system of record for the corpus: chunk text,
-- provenance, header fields, derived metadata, the full-text index, and
-- (later) embedding blobs. Chroma, when it exists, is a derived index
-- rebuilt from the embedding column at startup, not a second source of
-- truth.
--
-- A chunk's id is its rowid, assigned by AUTOINCREMENT so it is handed out
-- once and never reused, even after the row that held it is deleted. That id
-- is what a citation names and what Chroma will use as its vector id, so it
-- has to stay stable for the life of the database.

-- One row per transcript.
CREATE TABLE documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    source_path TEXT NOT NULL,
    subject TEXT NOT NULL,
    meeting_date TEXT NOT NULL,
    -- Written later by enrichment; absent until then.
    summary TEXT,
    -- Derived metadata, also written by enrichment.
    time_sensitivity TEXT,
    business_impact TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Bump updated_at whenever a row changes, unless the caller already set it.
CREATE TRIGGER documents_set_updated_at
AFTER UPDATE ON documents
FOR EACH ROW WHEN new.updated_at = old.updated_at
BEGIN
    UPDATE documents
    SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    WHERE id = new.id;
END;

-- Who was at a meeting, as rows rather than a delimited string.
CREATE TABLE attendees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    name TEXT NOT NULL
);

CREATE INDEX idx_attendees_document_id ON attendees (document_id);

-- The category list. document_topics is the join to documents.
CREATE TABLE topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE document_topics (
    document_id INTEGER NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    topic_id INTEGER NOT NULL REFERENCES topics (id) ON DELETE CASCADE,
    PRIMARY KEY (document_id, topic_id)
);

-- One row per retrievable span of text.
CREATE TABLE chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    -- Position of this chunk within its document, starting at 0.
    ordinal INTEGER NOT NULL,
    text TEXT NOT NULL,
    word_count INTEGER NOT NULL,
    -- The turn range, inclusive, this chunk spans in the source transcript.
    -- Null for a summary chunk, which is written about the document rather
    -- than taken from any span of it.
    turn_start INTEGER,
    turn_end INTEGER,
    kind TEXT NOT NULL CHECK (kind IN ('turn_window', 'summary')),
    -- Filled in by a later embedding pass; NULL until then.
    embedding BLOB,
    -- What produced the embedding. Recorded per chunk so a change of embedder
    -- is detectable rather than silently mixing vector spaces in one index.
    embedding_model TEXT,
    embedding_dim INTEGER,
    UNIQUE (document_id, ordinal),
    -- A turn window spans turns; a summary spans none. Keeping the two in
    -- step with kind is what stops a summary claiming a range it never had.
    CHECK (
        (kind = 'turn_window' AND turn_start IS NOT NULL AND turn_end IS NOT NULL)
        OR (kind = 'summary' AND turn_start IS NULL AND turn_end IS NULL)
    ),
    -- An embedding without provenance cannot be checked against the model in
    -- use, so the three travel together or not at all.
    CHECK (
        (embedding IS NULL AND embedding_model IS NULL AND embedding_dim IS NULL)
        OR (embedding IS NOT NULL AND embedding_model IS NOT NULL
            AND embedding_dim IS NOT NULL)
    )
);

CREATE INDEX idx_chunks_document_id ON chunks (document_id);

-- Full-text index over chunk text. It is an external-content table, kept in
-- step with chunks by the triggers below rather than by application code,
-- so nothing that writes a chunk has to remember the index exists.
CREATE VIRTUAL TABLE chunks_fts USING fts5(
    text,
    content='chunks',
    content_rowid='id'
);

CREATE TRIGGER chunks_after_insert
AFTER INSERT ON chunks
BEGIN
    INSERT INTO chunks_fts (rowid, text) VALUES (new.id, new.text);
END;

CREATE TRIGGER chunks_after_delete
AFTER DELETE ON chunks
BEGIN
    INSERT INTO chunks_fts (chunks_fts, rowid, text)
    VALUES ('delete', old.id, old.text);
END;

CREATE TRIGGER chunks_after_update
AFTER UPDATE ON chunks
BEGIN
    INSERT INTO chunks_fts (chunks_fts, rowid, text)
    VALUES ('delete', old.id, old.text);
    INSERT INTO chunks_fts (rowid, text) VALUES (new.id, new.text);
END;
