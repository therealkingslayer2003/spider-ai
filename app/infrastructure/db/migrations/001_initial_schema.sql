CREATE TABLE asset_type (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT
);

CREATE TABLE asset (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_type_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    added_at DATETIME NOT NULL,
    CONSTRAINT fk_asset_asset_type
        FOREIGN KEY (asset_type_id) REFERENCES asset_type (id) ON DELETE RESTRICT,
    CONSTRAINT uq_asset_type_name UNIQUE (asset_type_id, name)
);

CREATE TABLE research_artifact (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL,
    created_at DATETIME NOT NULL,
    data_as_of DATETIME,
    model TEXT,
    prompt_version TEXT,
    CONSTRAINT fk_research_artifact_asset
        FOREIGN KEY (asset_id) REFERENCES asset (id) ON DELETE RESTRICT
);

CREATE TABLE evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL,
    context_json TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    CONSTRAINT fk_evidence_asset
        FOREIGN KEY (asset_id) REFERENCES asset (id) ON DELETE RESTRICT
);

CREATE TABLE snapshot_research_artifact (
    research_artifact_id INTEGER PRIMARY KEY,
    evidence_id INTEGER NOT NULL UNIQUE,
    output_json TEXT NOT NULL,
    rationale TEXT,
    CONSTRAINT fk_snapshot_research_artifact_parent
        FOREIGN KEY (research_artifact_id)
        REFERENCES research_artifact (id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_snapshot_research_artifact_evidence
        FOREIGN KEY (evidence_id) REFERENCES evidence (id) ON DELETE RESTRICT
);

CREATE INDEX ix_research_artifact_asset_created_at
    ON research_artifact (asset_id, created_at DESC);

CREATE INDEX ix_evidence_asset_created_at
    ON evidence (asset_id, created_at DESC);
