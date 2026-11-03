CREATE TABLE niches (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  keywords_json TEXT NOT NULL DEFAULT '[]',
  language TEXT,
  country TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE channels (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  handle TEXT,
  description TEXT,
  country TEXT,
  default_language TEXT,
  thumbnail_url TEXT,
  uploads_playlist_id TEXT,
  is_own INTEGER NOT NULL DEFAULT 0,
  monitored INTEGER NOT NULL DEFAULT 0,
  niche_id INTEGER REFERENCES niches(id) ON DELETE SET NULL,
  text_refreshed_at TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE channel_snapshots (
  id INTEGER PRIMARY KEY,
  channel_id TEXT NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
  captured_at TEXT NOT NULL,
  subscriber_count INTEGER,
  view_count INTEGER,
  video_count INTEGER,
  UNIQUE (channel_id, captured_at)
);

CREATE TABLE videos (
  id TEXT PRIMARY KEY,
  channel_id TEXT NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  description TEXT,
  published_at TEXT NOT NULL,
  duration_seconds INTEGER,
  format TEXT NOT NULL CHECK (format IN ('short','long','live','unknown')),
  format_source TEXT NOT NULL CHECK (format_source IN ('analytics','duration','broadcast','missing')),
  language TEXT,
  country TEXT,
  thumbnail_url TEXT,
  category_id TEXT,
  text_refreshed_at TEXT NOT NULL,
  first_seen_at TEXT NOT NULL
);
CREATE INDEX idx_videos_channel_format ON videos(channel_id, format);
CREATE INDEX idx_videos_published ON videos(published_at);

CREATE TABLE snapshots (
  id INTEGER PRIMARY KEY,
  video_id TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
  captured_at TEXT NOT NULL,
  view_count INTEGER,
  like_count INTEGER,
  comment_count INTEGER,
  UNIQUE (video_id, captured_at)
);
CREATE INDEX idx_snapshots_video_time ON snapshots(video_id, captured_at);
CREATE INDEX idx_snapshots_time ON snapshots(captured_at);

CREATE TABLE searches (
  id INTEGER PRIMARY KEY,
  query TEXT NOT NULL,
  niche_id INTEGER REFERENCES niches(id) ON DELETE SET NULL,
  language TEXT,
  country TEXT,
  published_after TEXT,
  published_before TEXT,
  sort_order TEXT NOT NULL DEFAULT 'relevance',
  total_results_approx INTEGER,
  executed_at TEXT NOT NULL
);
CREATE INDEX idx_searches_query ON searches(query, executed_at);

CREATE TABLE search_results (
  search_id INTEGER NOT NULL REFERENCES searches(id) ON DELETE CASCADE,
  video_id TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
  rank INTEGER NOT NULL,
  PRIMARY KEY (search_id, video_id)
);

CREATE TABLE analytics_daily (
  channel_id TEXT NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
  day TEXT NOT NULL,
  content_type TEXT NOT NULL,
  views INTEGER,
  estimated_minutes_watched INTEGER,
  average_view_duration REAL,
  average_view_percentage REAL,
  subscribers_gained INTEGER,
  subscribers_lost INTEGER,
  fetched_at TEXT NOT NULL,
  PRIMARY KEY (channel_id, day, content_type)
);

CREATE TABLE oauth_channels (
  channel_id TEXT PRIMARY KEY REFERENCES channels(id) ON DELETE CASCADE,
  scopes TEXT NOT NULL,
  authorized_at TEXT NOT NULL,
  last_authorization_check_at TEXT NOT NULL
);

CREATE TABLE api_calls (
  id INTEGER PRIMARY KEY,
  called_at TEXT NOT NULL,
  quota_day TEXT NOT NULL,
  api TEXT NOT NULL,
  method TEXT NOT NULL,
  bucket TEXT NOT NULL,
  units INTEGER NOT NULL,
  status INTEGER,
  error_reason TEXT
);
CREATE INDEX idx_api_calls_day ON api_calls(quota_day, bucket);

CREATE TABLE api_cache (
  cache_key TEXT PRIMARY KEY,
  response_json TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);

CREATE TABLE jobs (
  name TEXT PRIMARY KEY,
  interval_minutes INTEGER NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  last_run_at TEXT,
  last_status TEXT,
  last_error TEXT
);

CREATE TABLE ai_generations (
  id INTEGER PRIMARY KEY,
  topic TEXT NOT NULL,
  format TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT,
  is_ai INTEGER NOT NULL,
  evidence_json TEXT NOT NULL,
  output_json TEXT NOT NULL,
  input_tokens INTEGER,
  output_tokens INTEGER,
  created_at TEXT NOT NULL
);
