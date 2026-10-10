CREATE TABLE filing_document_version (
    document_id TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    issuer_cik TEXT NOT NULL,
    accession_number TEXT NOT NULL,
    filename TEXT NOT NULL,
    published_at_utc TEXT NOT NULL,
    document_json TEXT NOT NULL,
    PRIMARY KEY (document_id, content_sha256)
);

CREATE TABLE filing_chunk (
    chunk_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    splitter_version TEXT NOT NULL,
    chunk_json TEXT NOT NULL,
    FOREIGN KEY (document_id, content_sha256)
        REFERENCES filing_document_version (document_id, content_sha256)
        ON DELETE RESTRICT
);

CREATE INDEX ix_filing_chunk_document
    ON filing_chunk (document_id, content_sha256);

CREATE TABLE filing_corpus (
    corpus_id TEXT PRIMARY KEY,
    asset TEXT NOT NULL,
    issuer_cik TEXT NOT NULL,
    as_of_utc TEXT NOT NULL,
    index_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('selected', 'indexing', 'ready', 'failed'))
);

CREATE TABLE filing_corpus_document (
    corpus_id TEXT NOT NULL REFERENCES filing_corpus (corpus_id) ON DELETE RESTRICT,
    document_id TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    position INTEGER NOT NULL,
    PRIMARY KEY (corpus_id, document_id, content_sha256),
    UNIQUE (corpus_id, position),
    FOREIGN KEY (document_id, content_sha256)
        REFERENCES filing_document_version (document_id, content_sha256)
        ON DELETE RESTRICT
);

CREATE TABLE filing_corpus_chunk (
    corpus_id TEXT NOT NULL REFERENCES filing_corpus (corpus_id) ON DELETE RESTRICT,
    chunk_id TEXT NOT NULL REFERENCES filing_chunk (chunk_id) ON DELETE RESTRICT,
    PRIMARY KEY (corpus_id, chunk_id)
);
