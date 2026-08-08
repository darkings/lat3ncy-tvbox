-- 008_audit_and_capabilities.sql: 审计日志与能力标签抽样证据表 (A21, A23)

CREATE TABLE IF NOT EXISTS audit_log (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_type  TEXT NOT NULL,          -- dedup_group|candidate_version|source
  entity_id    TEXT NOT NULL,
  action       TEXT NOT NULL,          -- primary_switch|state_change|override
  old_value    TEXT,
  new_value    TEXT,
  reason       TEXT,
  score_delta  REAL,
  acted_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_al_entity ON audit_log(entity_type, entity_id);

CREATE TABLE IF NOT EXISTS capability_sampling (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  fingerprint       TEXT NOT NULL,
  capability        TEXT NOT NULL,     -- movie|tv|anime|children|documentary|variety|cloud_drive|local|live
  hit_count         INT DEFAULT 0,
  sampling_evidence TEXT,              -- 抽样命中的样本标题与结构
  verified_at       TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_cs_fp_cap ON capability_sampling(fingerprint, capability);
