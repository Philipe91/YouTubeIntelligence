-- Fase 5: o que é só seu e não vem da API. Fica no estúdio e vale em qualquer modo.

ALTER TABLE recommendations ADD COLUMN difficulty TEXT CHECK (difficulty IN ('baixa','media','alta'));
ALTER TABLE recommendations ADD COLUMN confidence TEXT CHECK (confidence IN ('baixa','media','alta'));
ALTER TABLE recommendations ADD COLUMN favorite INTEGER NOT NULL DEFAULT 0;

CREATE TABLE keyword_favorites (
  channel_id TEXT NOT NULL REFERENCES managed_channels(id) ON DELETE CASCADE,
  term TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  PRIMARY KEY (channel_id, term)
);

CREATE TABLE lab_projects (
  id TEXT PRIMARY KEY,
  channel_id TEXT NOT NULL REFERENCES managed_channels(id) ON DELETE CASCADE,
  subject TEXT NOT NULL,
  recommendation_id TEXT REFERENCES recommendations(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX idx_lab_projects ON lab_projects(channel_id, updated_at);

CREATE TABLE lab_variations (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES lab_projects(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  title_eval_json TEXT NOT NULL,
  image_file TEXT,
  image_eval_json TEXT,
  note TEXT NOT NULL DEFAULT '',
  favorite INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE INDEX idx_lab_variations ON lab_variations(project_id, created_at);
