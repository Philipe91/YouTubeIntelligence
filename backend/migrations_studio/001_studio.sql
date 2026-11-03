-- Banco do estúdio: seus canais, planejamento e produção. Não guarda dados da API do YouTube.

CREATE TABLE studio_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE managed_channels (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  handle TEXT,
  youtube_channel_id TEXT UNIQUE,
  is_demo INTEGER NOT NULL DEFAULT 0,
  niche TEXT NOT NULL DEFAULT '',
  language TEXT NOT NULL DEFAULT 'pt',
  country TEXT NOT NULL DEFAULT '',
  audience TEXT NOT NULL DEFAULT '',
  positioning TEXT NOT NULL DEFAULT '',
  tone TEXT NOT NULL DEFAULT '',
  keywords_json TEXT NOT NULL DEFAULT '[]',
  avoid_json TEXT NOT NULL DEFAULT '[]',
  topic_backlog_json TEXT NOT NULL DEFAULT '[]',
  formats_json TEXT NOT NULL DEFAULT '["long","short"]',
  long_target_seconds INTEGER NOT NULL DEFAULT 600,
  short_target_seconds INTEGER NOT NULL DEFAULT 60,
  cadence_per_week REAL,
  auto_research TEXT NOT NULL DEFAULT 'on' CHECK (auto_research IN ('off','on')),
  auto_briefing TEXT NOT NULL DEFAULT 'on' CHECK (auto_briefing IN ('off','on')),
  auto_production TEXT NOT NULL DEFAULT 'manual' CHECK (auto_production IN ('off','manual','auto_simulated')),
  auto_package TEXT NOT NULL DEFAULT 'on' CHECK (auto_package IN ('off','on')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE competitors (
  id TEXT PRIMARY KEY,
  channel_id TEXT NOT NULL REFERENCES managed_channels(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  youtube_ref TEXT,
  notes TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  UNIQUE (channel_id, name)
);

CREATE TABLE video_history (
  id TEXT PRIMARY KEY,
  channel_id TEXT NOT NULL REFERENCES managed_channels(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  format TEXT NOT NULL CHECK (format IN ('short','long')),
  published_on TEXT NOT NULL,
  url TEXT,
  views INTEGER,
  result_notes TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL CHECK (source IN ('demo','manual')),
  created_at TEXT NOT NULL
);
CREATE INDEX idx_history_channel ON video_history(channel_id, published_on);

CREATE TABLE recommendations (
  id TEXT PRIMARY KEY,
  channel_id TEXT NOT NULL REFERENCES managed_channels(id) ON DELETE CASCADE,
  dedupe_key TEXT NOT NULL,
  subject TEXT NOT NULL,
  justification TEXT NOT NULL,
  sources_json TEXT NOT NULL,
  titles_json TEXT NOT NULL,
  thumbnail_idea TEXT NOT NULL,
  hook TEXT NOT NULL,
  format TEXT NOT NULL CHECK (format IN ('short','long')),
  duration_seconds INTEGER NOT NULL,
  target_audience TEXT NOT NULL,
  editorial_priority TEXT NOT NULL CHECK (editorial_priority IN ('alta','media','baixa')),
  facts_to_verify_json TEXT NOT NULL DEFAULT '[]',
  data_basis TEXT NOT NULL CHECK (data_basis IN ('editorial','demo_metrics','approved_metrics')),
  origin TEXT NOT NULL CHECK (origin IN ('regras','agente')),
  status TEXT NOT NULL DEFAULT 'nova' CHECK (status IN ('nova','aceita','descartada','em_producao','concluida')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (channel_id, dedupe_key)
);
CREATE INDEX idx_recommendations_channel ON recommendations(channel_id, status);

CREATE TABLE production_jobs (
  id TEXT PRIMARY KEY,
  channel_id TEXT NOT NULL REFERENCES managed_channels(id) ON DELETE CASCADE,
  recommendation_id TEXT REFERENCES recommendations(id) ON DELETE SET NULL,
  title TEXT NOT NULL,
  format TEXT NOT NULL,
  simulated INTEGER NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('awaiting_authorization','authorized','running','failed','delivered','package_ready','cancelled')),
  progress INTEGER NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
  step TEXT NOT NULL DEFAULT '',
  attempts INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 3,
  lease_owner TEXT,
  lease_token TEXT,
  lease_expires_at TEXT,
  requested_by TEXT NOT NULL,
  authorized_by TEXT,
  authorized_at TEXT,
  last_error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX idx_jobs_channel_state ON production_jobs(channel_id, state);
CREATE INDEX idx_jobs_state ON production_jobs(state);

CREATE TABLE job_events (
  id INTEGER PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES production_jobs(id) ON DELETE CASCADE,
  at TEXT NOT NULL,
  level TEXT NOT NULL CHECK (level IN ('info','warning','error')),
  kind TEXT NOT NULL,
  message TEXT NOT NULL,
  data_json TEXT
);
CREATE INDEX idx_events_job ON job_events(job_id, id);

CREATE TABLE job_artifacts (
  id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES production_jobs(id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK (kind IN ('video','short','thumbnail','script','audio','other')),
  path TEXT NOT NULL,
  label TEXT NOT NULL DEFAULT '',
  size_bytes INTEGER,
  sha256 TEXT,
  simulated INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE (job_id, path)
);

-- Não existe estado "publicado": o pacote só pode ficar pronto para revisão humana.
CREATE TABLE publish_packages (
  id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL UNIQUE REFERENCES production_jobs(id) ON DELETE CASCADE,
  channel_id TEXT NOT NULL REFERENCES managed_channels(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  tags_json TEXT NOT NULL,
  video_artifact_id TEXT NOT NULL REFERENCES job_artifacts(id),
  thumbnail_artifact_id TEXT REFERENCES job_artifacts(id),
  checklist_json TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'ready_for_human_review' CHECK (state = 'ready_for_human_review'),
  created_at TEXT NOT NULL
);

CREATE TABLE calendar_entries (
  id TEXT PRIMARY KEY,
  channel_id TEXT NOT NULL REFERENCES managed_channels(id) ON DELETE CASCADE,
  scheduled_on TEXT NOT NULL,
  title TEXT NOT NULL,
  format TEXT NOT NULL CHECK (format IN ('short','long')),
  status TEXT NOT NULL DEFAULT 'planejado' CHECK (status IN ('planejado','em_producao','pronto_para_revisao','publicado_manualmente','cancelado')),
  recommendation_id TEXT REFERENCES recommendations(id) ON DELETE SET NULL,
  job_id TEXT REFERENCES production_jobs(id) ON DELETE SET NULL,
  notes TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX idx_calendar_channel_day ON calendar_entries(channel_id, scheduled_on);

CREATE TABLE idempotency_records (
  operation TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  response_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (operation, idempotency_key)
);

CREATE TABLE agent_activity (
  agent_id TEXT NOT NULL,
  channel_id TEXT NOT NULL REFERENCES managed_channels(id) ON DELETE CASCADE,
  last_operation TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  PRIMARY KEY (agent_id, channel_id)
);
