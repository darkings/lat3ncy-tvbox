-- Human approval is bound to immutable content, never to a mutable URL.
CREATE TABLE IF NOT EXISTS dependency_asset_approval (
    content_sha256 TEXT PRIMARY KEY,
    asset_type TEXT NOT NULL DEFAULT 'jar',
    upstream_repo TEXT NOT NULL,
    upstream_commit TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('approved','rejected','revoked','expired')),
    review_reason TEXT NOT NULL,
    approved_by TEXT NOT NULL,
    approved_at TEXT,
    expires_at TEXT,
    revoked_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dependency_asset_approval_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_sha256 TEXT NOT NULL,
    old_status TEXT,
    new_status TEXT NOT NULL,
    actor TEXT NOT NULL,
    reason TEXT NOT NULL,
    upstream_repo TEXT,
    upstream_commit TEXT,
    expires_at TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dependency_approval_status
    ON dependency_asset_approval(status, expires_at);
CREATE INDEX IF NOT EXISTS idx_dependency_approval_event_sha
    ON dependency_asset_approval_event(content_sha256, created_at);
