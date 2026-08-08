CREATE TABLE IF NOT EXISTS drpy_test_result (
  id          INTEGER PRIMARY KEY,
  fingerprint TEXT NOT NULL,
  test_type   TEXT NOT NULL,   -- search|detail|episode|playurl
  keyword     TEXT,            -- 搜索词或测试内容标题
  success     INT NOT NULL,    -- 1/0
  result_count INT,            -- 搜索结果数 / 选集数
  latency_ms  INT,
  error       TEXT,
  tested_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dtr_fp ON drpy_test_result(fingerprint, test_type);
CREATE INDEX IF NOT EXISTS idx_dtr_at ON drpy_test_result(tested_at);
