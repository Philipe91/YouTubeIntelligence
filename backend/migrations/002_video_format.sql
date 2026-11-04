-- Formato "indeterminate": vídeo curto sem dados que confirmem se é Short.
-- Vídeos reais antes tratados como Short só pela duração passam a indeterminados.
-- Dados fictícios mantêm o formato inventado, com origem própria.

CREATE TABLE videos_new (
  id TEXT PRIMARY KEY,
  channel_id TEXT NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  description TEXT,
  published_at TEXT NOT NULL,
  duration_seconds INTEGER,
  format TEXT NOT NULL CHECK (format IN ('short','long','live','indeterminate','unknown')),
  format_source TEXT NOT NULL CHECK (format_source IN ('analytics','duration','aspect_ratio','broadcast','fictional','missing')),
  language TEXT,
  country TEXT,
  thumbnail_url TEXT,
  category_id TEXT,
  text_refreshed_at TEXT NOT NULL,
  first_seen_at TEXT NOT NULL
);

INSERT INTO videos_new
SELECT id, channel_id, title, description, published_at, duration_seconds,
       CASE WHEN id NOT LIKE 'DEMO\_%' ESCAPE '\' AND format = 'short' AND format_source = 'duration' THEN 'indeterminate' ELSE format END,
       CASE WHEN id LIKE 'DEMO\_%' ESCAPE '\' THEN 'fictional' ELSE format_source END,
       language, country, thumbnail_url, category_id, text_refreshed_at, first_seen_at
FROM videos;

DROP TABLE videos;
ALTER TABLE videos_new RENAME TO videos;
CREATE INDEX idx_videos_channel_format ON videos(channel_id, format);
CREATE INDEX idx_videos_published ON videos(published_at);
