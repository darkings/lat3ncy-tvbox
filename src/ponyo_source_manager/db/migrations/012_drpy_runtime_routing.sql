-- Persist DRPY runtime routing audit per run without changing source state.
ALTER TABLE drpy_run ADD COLUMN discovered_sources INTEGER NOT NULL DEFAULT 0;
ALTER TABLE drpy_run ADD COLUMN routing_counts_json TEXT NOT NULL DEFAULT '{}';
