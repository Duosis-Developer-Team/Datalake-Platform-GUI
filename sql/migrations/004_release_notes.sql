-- 004_release_notes.sql — AI ile üretilen release note'lar (TASK-64 faz 2).
-- Her platform_releases satırının en fazla bir notu olur (release_id UNIQUE).
-- body: yayınlanan not. draft_body: onay bekleyen taslak, panelde asla gösterilmez.

CREATE TABLE IF NOT EXISTS release_notes (
    id                serial PRIMARY KEY,
    release_id        integer NOT NULL UNIQUE REFERENCES platform_releases(id) ON DELETE CASCADE,
    headline          text,
    body              jsonb NOT NULL,
    source            varchar(16) NOT NULL DEFAULT 'auto',
    draft_headline    text,
    draft_body        jsonb,
    model             varchar(64),
    input_fingerprint varchar(64) NOT NULL,
    generated_at      timestamptz NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_release_notes_release ON release_notes(release_id);
