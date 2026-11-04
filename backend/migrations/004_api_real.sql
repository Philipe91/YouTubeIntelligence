-- Fase 6: dados reais. Testes de conexão, proveniência das pesquisas, itens salvos por tipo e agendador.
-- O agendador nasce sem aprovação: real_enabled = 0 até o dono aprovar os limites.

CREATE TABLE api_checks (
  id INTEGER PRIMARY KEY,
  checked_at TEXT NOT NULL,
  ok INTEGER NOT NULL,
  kind TEXT NOT NULL,
  message TEXT NOT NULL,
  target TEXT NOT NULL CHECK (target IN ('google','simulada')),
  details_json TEXT NOT NULL DEFAULT '{}'
);

ALTER TABLE research_runs ADD COLUMN provenance_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE research_runs ADD COLUMN schedule_id TEXT;

-- `title` só guarda texto do dono. Vídeo e canal salvos guardam o ID: o texto da API continua sujeito à retenção.
ALTER TABLE editorial_opportunities ADD COLUMN item_type TEXT NOT NULL DEFAULT 'tema';
ALTER TABLE editorial_opportunities ADD COLUMN channel_ref TEXT;
ALTER TABLE editorial_opportunities ADD COLUMN niche TEXT;
ALTER TABLE editorial_opportunities ADD COLUMN subniche TEXT;
ALTER TABLE editorial_opportunities ADD COLUMN run_id TEXT;

CREATE TABLE research_schedules (
  id TEXT PRIMARY KEY,
  managed_channel_id TEXT NOT NULL,
  signature TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('videos','channels','recent','emerging')),
  query TEXT NOT NULL,
  filters_json TEXT NOT NULL DEFAULT '{}',
  interval_hours INTEGER NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  paused_reason TEXT,
  consecutive_errors INTEGER NOT NULL DEFAULT 0,
  next_run_at TEXT NOT NULL,
  last_run_at TEXT,
  last_status TEXT,
  last_error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (managed_channel_id, signature)
);
CREATE INDEX idx_schedules_due ON research_schedules(enabled, next_run_at);

CREATE TABLE schedule_events (
  id INTEGER PRIMARY KEY,
  schedule_id TEXT REFERENCES research_schedules(id) ON DELETE CASCADE,
  at TEXT NOT NULL,
  status TEXT NOT NULL,
  run_id TEXT,
  message TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_schedule_events ON schedule_events(schedule_id, at);

CREATE TABLE automation_settings (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  real_enabled INTEGER NOT NULL DEFAULT 0,
  max_searches_per_day INTEGER NOT NULL DEFAULT 0,
  approved_at TEXT,
  approved_by TEXT,
  paused_until TEXT,
  paused_reason TEXT
);
INSERT INTO automation_settings (id) VALUES (1);
