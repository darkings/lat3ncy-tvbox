CREATE TABLE IF NOT EXISTS raw_source (
  id            INTEGER PRIMARY KEY,
  import_batch  TEXT NOT NULL,
  origin        TEXT NOT NULL,
  site_key      TEXT NOT NULL,
  name          TEXT,
  type          INTEGER,
  api           TEXT,
  ext           TEXT,
  raw_json      TEXT NOT NULL,
  UNIQUE(import_batch, origin, site_key)
);
CREATE TABLE IF NOT EXISTS norm_source (
  id            INTEGER PRIMARY KEY,
  raw_id        INTEGER NOT NULL REFERENCES raw_source(id),
  fingerprint   TEXT NOT NULL,
  api_host      TEXT,
  required_urls TEXT,
  jar_md5       TEXT,
  spider_class  TEXT,
  category      TEXT,
  capabilities  TEXT
);
CREATE TABLE IF NOT EXISTS dedup_group (
  fingerprint    TEXT PRIMARY KEY,
  member_count   INTEGER NOT NULL,
  primary_raw_id INTEGER REFERENCES raw_source(id),
  member_ids     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS health_snapshot (
  id            INTEGER PRIMARY KEY,
  site_key      TEXT NOT NULL,
  verdict       TEXT,
  urls          TEXT,
  captured_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS name_map (
  site_key TEXT PRIMARY KEY,
  old_name TEXT,
  new_name TEXT,
  verdict  TEXT
);
CREATE TABLE IF NOT EXISTS list_state (
  fingerprint TEXT PRIMARY KEY,
  state       TEXT NOT NULL,
  reason      TEXT,
  updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_norm_fp   ON norm_source(fingerprint);
CREATE INDEX IF NOT EXISTS idx_norm_cat  ON norm_source(category);
CREATE INDEX IF NOT EXISTS idx_raw_batch ON raw_source(import_batch);
