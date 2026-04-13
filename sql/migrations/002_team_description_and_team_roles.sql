-- Team metadata and roles assigned to teams (members inherit via permission resolution).
ALTER TABLE teams ADD COLUMN IF NOT EXISTS description TEXT;

CREATE TABLE IF NOT EXISTS team_roles (
    team_id INT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    role_id INT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    PRIMARY KEY (team_id, role_id)
);

CREATE INDEX IF NOT EXISTS idx_team_roles_team ON team_roles(team_id);
