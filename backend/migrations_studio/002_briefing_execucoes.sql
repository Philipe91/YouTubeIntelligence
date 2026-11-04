-- Briefing aprovado, histórico de execuções, alertas reconhecíveis e perfil de pipeline.

CREATE TABLE recommendations_new (
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
  origin TEXT NOT NULL CHECK (origin IN ('regras','agente','dono')),
  status TEXT NOT NULL DEFAULT 'nova' CHECK (status IN ('nova','aceita','descartada','em_producao','concluida')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (channel_id, dedupe_key)
);
INSERT INTO recommendations_new SELECT id, channel_id, dedupe_key, subject, justification, sources_json, titles_json, thumbnail_idea, hook,
  format, duration_seconds, target_audience, editorial_priority, facts_to_verify_json, data_basis, origin, status, created_at, updated_at
  FROM recommendations;
DROP TABLE recommendations;
ALTER TABLE recommendations_new RENAME TO recommendations;
CREATE INDEX idx_recommendations_channel ON recommendations(channel_id, status);

CREATE TABLE briefings (
  id TEXT PRIMARY KEY,
  channel_id TEXT NOT NULL REFERENCES managed_channels(id) ON DELETE CASCADE,
  recommendation_id TEXT NOT NULL UNIQUE REFERENCES recommendations(id) ON DELETE CASCADE,
  chosen_title TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  approved_by TEXT NOT NULL,
  approved_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

ALTER TABLE production_jobs ADD COLUMN briefing_id TEXT REFERENCES briefings(id) ON DELETE SET NULL;

CREATE TABLE job_attempts (
  id INTEGER PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES production_jobs(id) ON DELETE CASCADE,
  number INTEGER NOT NULL,
  agent_id TEXT NOT NULL,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  outcome TEXT NOT NULL DEFAULT 'em_andamento' CHECK (outcome IN ('em_andamento','entregue','falhou','prazo_vencido','cancelada')),
  error TEXT
);
CREATE INDEX idx_attempts_job ON job_attempts(job_id, number);

ALTER TABLE job_events ADD COLUMN acknowledged_at TEXT;
ALTER TABLE managed_channels ADD COLUMN pipeline_profile TEXT NOT NULL DEFAULT 'simulado';
