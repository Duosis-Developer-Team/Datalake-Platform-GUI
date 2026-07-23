-- Platform versioning: deployed versions, their changelog entries, and per-service deploy events.
CREATE TABLE IF NOT EXISTS platform_releases (
    id          SERIAL PRIMARY KEY,
    version     VARCHAR(32) UNIQUE NOT NULL,
    released_at DATE NOT NULL,
    title       TEXT,
    notes       TEXT,
    source      VARCHAR(16) NOT NULL DEFAULT 'deploy',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS release_changes (
    id          SERIAL PRIMARY KEY,
    release_id  INT NOT NULL REFERENCES platform_releases(id) ON DELETE CASCADE,
    change_type VARCHAR(16) NOT NULL DEFAULT 'other',
    summary     TEXT NOT NULL,
    commit_sha  VARCHAR(40),
    scope       VARCHAR(64)
);

CREATE TABLE IF NOT EXISTS service_deployments (
    id          SERIAL PRIMARY KEY,
    service     VARCHAR(64) NOT NULL,
    version     VARCHAR(64) NOT NULL,
    git_sha     VARCHAR(40),
    image_tag   VARCHAR(128),
    environment VARCHAR(32) NOT NULL DEFAULT 'production',
    started_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_release_changes_release ON release_changes(release_id);
CREATE INDEX IF NOT EXISTS idx_service_deployments_started ON service_deployments(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_service_deployments_version ON service_deployments(version);
