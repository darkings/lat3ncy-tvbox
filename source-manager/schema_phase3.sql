CREATE TABLE IF NOT EXISTS security_finding (
  id INTEGER PRIMARY KEY, fingerprint TEXT NOT NULL, target_url TEXT,
  asset_type TEXT, rule_id TEXT NOT NULL, severity TEXT NOT NULL,
  evidence TEXT, scanned_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sf_fp ON security_finding(fingerprint, severity);
CREATE TABLE IF NOT EXISTS conn_probe (
  id INTEGER PRIMARY KEY, fingerprint TEXT NOT NULL, target_url TEXT NOT NULL,
  timeslot TEXT NOT NULL, dns_ok INT, tcp_ok INT, tls_ok INT,
  http_status INT, latency_ms INT, ok INT NOT NULL, err TEXT, probed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cp_fp ON conn_probe(fingerprint, timeslot);
