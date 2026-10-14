-- Keep the parsed plaintext and its text-only token count addressable in SQL.
-- Defaults permit adding NOT NULL columns to an existing SQLite table; the
-- backfill replaces them before the migration is recorded as applied.
ALTER TABLE filing_chunk ADD COLUMN text TEXT NOT NULL DEFAULT '';
ALTER TABLE filing_chunk ADD COLUMN token_count INTEGER NOT NULL DEFAULT 0;

UPDATE filing_chunk
SET text = json_extract(chunk_json, '$.text'),
    token_count = json_extract(chunk_json, '$.token_count'),
    chunk_json = json_remove(chunk_json, '$.text', '$.token_count');

CREATE TRIGGER filing_chunk_content_insert
BEFORE INSERT ON filing_chunk
WHEN NEW.text = '' OR NEW.token_count <= 0
BEGIN
    SELECT RAISE(ABORT, 'Filing chunk requires text and a positive token count');
END;

CREATE TRIGGER filing_chunk_content_update
BEFORE UPDATE ON filing_chunk
WHEN NEW.text = '' OR NEW.token_count <= 0
BEGIN
    SELECT RAISE(ABORT, 'Filing chunk requires text and a positive token count');
END;
