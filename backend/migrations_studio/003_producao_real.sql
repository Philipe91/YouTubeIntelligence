-- Roteiro, etapas reais, validação do vídeo e revisão humana.

CREATE TABLE job_scripts (
  job_id TEXT PRIMARY KEY REFERENCES production_jobs(id) ON DELETE CASCADE,
  payload_json TEXT NOT NULL,
  submitted_by TEXT NOT NULL,
  submitted_at TEXT NOT NULL
);

CREATE TABLE job_stages (
  job_id TEXT NOT NULL REFERENCES production_jobs(id) ON DELETE CASCADE,
  stage TEXT NOT NULL,
  position INTEGER NOT NULL,
  label TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pendente','em_andamento','concluida','falhou')),
  detail TEXT NOT NULL DEFAULT '',
  done INTEGER,
  total INTEGER,
  started_at TEXT,
  ended_at TEXT,
  PRIMARY KEY (job_id, stage)
);

CREATE TABLE job_validation (
  job_id TEXT PRIMARY KEY REFERENCES production_jobs(id) ON DELETE CASCADE,
  ok INTEGER NOT NULL,
  report_json TEXT NOT NULL,
  validated_by TEXT NOT NULL,
  validated_at TEXT NOT NULL
);

ALTER TABLE production_jobs ADD COLUMN review_status TEXT;
ALTER TABLE production_jobs ADD COLUMN review_note TEXT;
ALTER TABLE production_jobs ADD COLUMN reviewed_at TEXT;
