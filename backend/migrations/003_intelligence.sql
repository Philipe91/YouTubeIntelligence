-- Fase 5: inteligência por canal. Fica no banco de pesquisa de cada modo, para dado fictício nunca
-- se misturar com dado real. Só guarda IDs de vídeos e canais: o texto da API continua em `videos`
-- e `channels`, sujeito à retenção. `managed_channel_id` aponta para o banco do estúdio.

CREATE TABLE intel_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE research_runs (
  id TEXT PRIMARY KEY,
  managed_channel_id TEXT,
  kind TEXT NOT NULL CHECK (kind IN ('videos','channels','recent','emerging')),
  query TEXT NOT NULL,
  filters_json TEXT NOT NULL DEFAULT '{}',
  data_origin TEXT NOT NULL CHECK (data_origin IN ('demo','youtube')),
  total_results_approx INTEGER,
  result_count INTEGER NOT NULL DEFAULT 0,
  saved_name TEXT,
  executed_at TEXT NOT NULL
);
CREATE INDEX idx_runs_channel_time ON research_runs(managed_channel_id, executed_at);
CREATE INDEX idx_runs_saved ON research_runs(saved_name);

CREATE TABLE research_items (
  run_id TEXT NOT NULL REFERENCES research_runs(id) ON DELETE CASCADE,
  item_type TEXT NOT NULL CHECK (item_type IN ('video','channel')),
  item_id TEXT NOT NULL,
  rank INTEGER NOT NULL,
  PRIMARY KEY (run_id, item_type, item_id)
);
CREATE INDEX idx_research_items_item ON research_items(item_type, item_id);

CREATE TABLE keyword_lookups (
  id INTEGER PRIMARY KEY,
  managed_channel_id TEXT,
  term TEXT NOT NULL,
  language TEXT,
  data_origin TEXT NOT NULL CHECK (data_origin IN ('demo','youtube')),
  looked_up_at TEXT NOT NULL
);
CREATE INDEX idx_keyword_lookups ON keyword_lookups(managed_channel_id, looked_up_at);

-- Termos pelos quais as pessoas acharam os vídeos do próprio canal (YouTube Analytics, com OAuth).
CREATE TABLE own_search_terms (
  channel_id TEXT NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
  term TEXT NOT NULL,
  views INTEGER,
  minutes_watched INTEGER,
  period_start TEXT NOT NULL,
  period_end TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  PRIMARY KEY (channel_id, term, period_end)
);

CREATE TABLE study_videos (
  managed_channel_id TEXT NOT NULL,
  video_id TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
  origin TEXT NOT NULL DEFAULT 'explorer' CHECK (origin IN ('explorer','competidor','pesquisa')),
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  PRIMARY KEY (managed_channel_id, video_id)
);

CREATE TABLE editorial_opportunities (
  id TEXT PRIMARY KEY,
  managed_channel_id TEXT NOT NULL,
  title TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  video_id TEXT REFERENCES videos(id) ON DELETE SET NULL,
  status TEXT NOT NULL DEFAULT 'aberta' CHECK (status IN ('aberta','virou_ideia','descartada')),
  recommendation_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX idx_editorial_opportunities ON editorial_opportunities(managed_channel_id, status);

CREATE TABLE coach_conversations (
  id TEXT PRIMARY KEY,
  managed_channel_id TEXT NOT NULL,
  title TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX idx_coach_conversations ON coach_conversations(managed_channel_id, updated_at);

CREATE TABLE coach_messages (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES coach_conversations(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('user','assistant')),
  content_json TEXT NOT NULL,
  provider TEXT,
  model TEXT,
  is_ai INTEGER NOT NULL DEFAULT 0,
  input_tokens INTEGER,
  output_tokens INTEGER,
  cost_usd REAL,
  created_at TEXT NOT NULL
);
CREATE INDEX idx_coach_messages ON coach_messages(conversation_id, created_at);

CREATE TABLE coach_tool_calls (
  id INTEGER PRIMARY KEY,
  message_id TEXT NOT NULL REFERENCES coach_messages(id) ON DELETE CASCADE,
  tool TEXT NOT NULL,
  args_json TEXT NOT NULL,
  ok INTEGER NOT NULL,
  summary TEXT NOT NULL,
  at TEXT NOT NULL
);
