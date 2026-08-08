-- 007_discovery_collector.sql: 多入口采集器、来源追溯与依赖关系数据模型

CREATE TABLE IF NOT EXISTS discovery_batch (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  connector     TEXT NOT NULL,          -- github|subscription|repo|seed
  query         TEXT,
  started_at    TEXT NOT NULL,
  finished_at   TEXT,
  status        TEXT DEFAULT 'running', -- running|success|failed|partial
  request_count INT DEFAULT 0,
  error_count   INT DEFAULT 0,
  rate_limit_remaining INT
);

CREATE TABLE IF NOT EXISTS upstream_resource (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  source_type     TEXT NOT NULL,        -- github_repo|subscription_url|manual_seed
  repo            TEXT,
  branch          TEXT,
  path            TEXT,
  url             TEXT NOT NULL,
  etag            TEXT,
  commit_sha      TEXT,
  content_sha256  TEXT,
  first_seen_at   TEXT NOT NULL,
  last_seen_at    TEXT NOT NULL,
  last_changed_at TEXT NOT NULL,
  trust_level     TEXT DEFAULT 'public'
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ur_url_path ON upstream_resource(url, path);

CREATE TABLE IF NOT EXISTS candidate_version (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  upstream_id      INTEGER REFERENCES upstream_resource(id),
  fingerprint      TEXT NOT NULL,
  site_key         TEXT,
  name             TEXT,
  api              TEXT,
  ext              TEXT,
  raw_json         TEXT NOT NULL,
  discovered_at    TEXT NOT NULL,
  validation_state TEXT DEFAULT 'candidate', -- candidate|allow|deny
  rejection_reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_cv_fp ON candidate_version(fingerprint);

CREATE TABLE IF NOT EXISTS dependency_edge (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  parent_resource_id INTEGER NOT NULL REFERENCES upstream_resource(id),
  child_url          TEXT NOT NULL,
  relation_type      TEXT DEFAULT 'script', -- script|jar|json|m3u
  depth              INT DEFAULT 1
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_de_parent_child ON dependency_edge(parent_resource_id, child_url);
