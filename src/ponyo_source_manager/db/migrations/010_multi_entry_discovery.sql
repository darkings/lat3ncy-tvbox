-- GitHub 增量采集与 MacCMS 预筛的隔离证据表。
-- 这里只保存“发现了什么”和探测证据；不得直接改变 list_state。
CREATE TABLE IF NOT EXISTS discovery_cursor (
    connector TEXT NOT NULL,
    scope TEXT NOT NULL,
    revision TEXT,
    pending_revision TEXT,
    position INTEGER NOT NULL DEFAULT 0,
    etag TEXT,
    checked_at TEXT NOT NULL,
    changed_at TEXT,
    last_error TEXT,
    PRIMARY KEY (connector, scope)
);

CREATE TABLE IF NOT EXISTS discovered_artifact (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    connector TEXT NOT NULL,
    scope TEXT NOT NULL,
    artifact_url TEXT NOT NULL,
    effective_url TEXT,
    artifact_kind TEXT NOT NULL,
    revision TEXT,
    content_sha256 TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    last_changed_at TEXT NOT NULL,
    UNIQUE (connector, scope, artifact_url)
);

CREATE INDEX IF NOT EXISTS idx_discovered_artifact_kind
    ON discovered_artifact(artifact_kind, last_seen_at);

CREATE TABLE IF NOT EXISTS maccms_probe_result (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    keyword TEXT NOT NULL,
    search_ok INTEGER NOT NULL DEFAULT 0,
    keyword_hit INTEGER NOT NULL DEFAULT 0,
    detail_ok INTEGER NOT NULL DEFAULT 0,
    playable_url_count INTEGER NOT NULL DEFAULT 0,
    failure_stage TEXT,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    probed_at TEXT NOT NULL,
    UNIQUE (run_id, endpoint, keyword)
);
