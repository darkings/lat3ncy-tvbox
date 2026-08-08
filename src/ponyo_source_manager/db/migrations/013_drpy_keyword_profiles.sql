-- Persist lane-aware keyword coverage for historical acceptance audits.
ALTER TABLE drpy_run ADD COLUMN keyword_profile_counts_json TEXT NOT NULL DEFAULT '{}';
