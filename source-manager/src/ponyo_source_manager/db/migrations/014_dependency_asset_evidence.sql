-- Root-level TVBox spider/JAR inheritance and static validation evidence.
-- Assets remain data only: this table never authorizes execution.
CREATE TABLE IF NOT EXISTS dependency_asset_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint TEXT NOT NULL,
    config_origin TEXT NOT NULL,
    source_field TEXT NOT NULL,
    effective_url TEXT NOT NULL DEFAULT '',
    asset_type TEXT NOT NULL,
    declared_md5 TEXT,
    resolution_status TEXT NOT NULL,
    inherited_from_root INTEGER NOT NULL DEFAULT 0,
    fetch_status TEXT NOT NULL DEFAULT 'pending',
    actual_md5 TEXT,
    content_sha256 TEXT,
    size_bytes INTEGER,
    archive_entry_count INTEGER,
    validation_status TEXT NOT NULL DEFAULT 'pending',
    last_error TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    scanned_at TEXT,
    UNIQUE(fingerprint, config_origin, source_field, effective_url)
);

CREATE INDEX IF NOT EXISTS idx_dependency_asset_fingerprint
    ON dependency_asset_evidence(fingerprint, asset_type, validation_status);

CREATE INDEX IF NOT EXISTS idx_dependency_asset_url
    ON dependency_asset_evidence(effective_url, last_seen_at);
