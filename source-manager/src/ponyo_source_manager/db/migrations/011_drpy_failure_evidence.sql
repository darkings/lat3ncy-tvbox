-- Stage-specific DRPY evidence. Existing rows remain valid and are classified
-- only on new runs; discovery and probing still must not mutate list_state.
CREATE TABLE IF NOT EXISTS drpy_test_result (
    id INTEGER PRIMARY KEY,
    fingerprint TEXT NOT NULL,
    test_type TEXT NOT NULL,
    keyword TEXT,
    success INT NOT NULL,
    result_count INT,
    latency_ms INT,
    error TEXT,
    tested_at TEXT NOT NULL
);

ALTER TABLE drpy_test_result ADD COLUMN failure_stage TEXT;
ALTER TABLE drpy_test_result ADD COLUMN run_id TEXT;
ALTER TABLE drpy_test_result ADD COLUMN adapter_version TEXT;
ALTER TABLE drpy_test_result ADD COLUMN evidence_json TEXT NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_dtr_run_stage
    ON drpy_test_result(run_id, failure_stage);

CREATE TABLE IF NOT EXISTS drpy_run (
    run_id TEXT PRIMARY KEY,
    adapter_version TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    total_sources INTEGER NOT NULL DEFAULT 0,
    tested_sources INTEGER NOT NULL DEFAULT 0,
    passed_sources INTEGER NOT NULL DEFAULT 0,
    failed_sources INTEGER NOT NULL DEFAULT 0,
    failure_counts_json TEXT NOT NULL DEFAULT '{}'
);
