CREATE TABLE IF NOT EXISTS media_probe (
  id           INTEGER PRIMARY KEY,
  fingerprint  TEXT NOT NULL,
  content_title TEXT,
  play_url     TEXT,
  width        INT,
  height       INT,
  video_codec  TEXT,           -- h264|hevc|av1|...
  video_bitrate INT,           -- bps
  audio_codec  TEXT,           -- aac|mp3|...
  frame_rate   REAL,
  duration_s   REAL,
  quality_tier TEXT,            -- sd|hd|fhd|uhd
  success      INT NOT NULL,
  error        TEXT,
  probed_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mp_fp ON media_probe(fingerprint, quality_tier);
