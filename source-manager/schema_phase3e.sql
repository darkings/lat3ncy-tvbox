CREATE TABLE IF NOT EXISTS score_snapshot (
  id            INTEGER PRIMARY KEY,
  fingerprint   TEXT NOT NULL,
  timeslot      TEXT,              -- morning|noon|evening|night|daily
  play_success  REAL,              -- 播放成功率 0-1
  stability     REAL,              -- 多时段稳定性 0-1
  speed_score   REAL,              -- 首帧与读取速度得分 0-1
  func_score    REAL,              -- 搜索/详情/选集成功率 0-1
  quality_score REAL,              -- 高清比例与内容质量 0-1
  total_score   REAL NOT NULL,     -- 加权总分 0-100
  p50_ms        INT,               -- 延迟中位数
  p95_ms        INT,               -- 延迟 P95
  peak_speed_ms INT,               -- 晚高峰速度
  consecutive_fail INT DEFAULT 0,  -- 连续失败次数
  scored_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ss_fp ON score_snapshot(fingerprint, scored_at);
CREATE INDEX IF NOT EXISTS idx_ss_total ON score_snapshot(total_score DESC);

CREATE TABLE IF NOT EXISTS promotion_log (
  id          INTEGER PRIMARY KEY,
  fingerprint TEXT NOT NULL,
  action      TEXT NOT NULL,       -- promote|demote|hold
  old_state   TEXT,
  new_state   TEXT,
  reason      TEXT,
  acted_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pl_fp ON promotion_log(fingerprint);
