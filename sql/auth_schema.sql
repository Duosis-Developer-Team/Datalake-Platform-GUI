-- Reference DDL for the dedicated Auth PostgreSQL database (public schema).
-- Runtime creation uses migration.py (CREATE IF NOT EXISTS + versioning).

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INT PRIMARY KEY,
    description VARCHAR(255) NOT NULL,
    applied_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    username      VARCHAR(150) UNIQUE NOT NULL,
    display_name  VARCHAR(255),
    email         VARCHAR(255),
    password_hash VARCHAR(255),
    source        VARCHAR(20) DEFAULT 'local',
    ldap_dn       TEXT,
    is_active     BOOLEAN DEFAULT TRUE,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS roles (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    is_system   BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS permissions (
    id             SERIAL PRIMARY KEY,
    code           VARCHAR(150) UNIQUE NOT NULL,
    name           VARCHAR(200) NOT NULL,
    description    TEXT,
    parent_id      INT REFERENCES permissions(id) ON DELETE CASCADE,
    resource_type  VARCHAR(30) NOT NULL DEFAULT 'page',
    route_pattern  VARCHAR(255),
    component_id   VARCHAR(150),
    icon           VARCHAR(100),
    sort_order     INT DEFAULT 0,
    is_dynamic     BOOLEAN DEFAULT FALSE,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS role_permissions (
    role_id       INT REFERENCES roles(id) ON DELETE CASCADE,
    permission_id INT REFERENCES permissions(id) ON DELETE CASCADE,
    can_view      BOOLEAN DEFAULT FALSE,
    can_edit      BOOLEAN DEFAULT FALSE,
    can_export    BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE IF NOT EXISTS user_roles (
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    role_id INT REFERENCES roles(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, role_id)
);

CREATE TABLE IF NOT EXISTS ldap_config (
    id               SERIAL PRIMARY KEY,
    name             VARCHAR(100) NOT NULL,
    server_primary   VARCHAR(255) NOT NULL,
    server_secondary VARCHAR(255),
    port             INT DEFAULT 389,
    use_ssl          BOOLEAN DEFAULT FALSE,
    bind_dn          TEXT NOT NULL,
    bind_password    TEXT NOT NULL,
    search_base_dn   TEXT NOT NULL,
    user_search_filter  VARCHAR(255) DEFAULT '(sAMAccountName={username})',
    group_search_filter VARCHAR(255) DEFAULT '(objectClass=group)',
    is_active        BOOLEAN DEFAULT TRUE,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ldap_group_role_mapping (
    id             SERIAL PRIMARY KEY,
    ldap_config_id INT REFERENCES ldap_config(id) ON DELETE CASCADE,
    ldap_group_dn  TEXT NOT NULL,
    role_id        INT REFERENCES roles(id) ON DELETE CASCADE,
    UNIQUE (ldap_config_id, ldap_group_dn, role_id)
);

CREATE TABLE IF NOT EXISTS teams (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(150) NOT NULL,
    description TEXT,
    parent_id   INT REFERENCES teams(id) ON DELETE SET NULL,
    created_by  INT REFERENCES users(id),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS team_roles (
    team_id INT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    role_id INT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    PRIMARY KEY (team_id, role_id)
);

CREATE TABLE IF NOT EXISTS team_members (
    team_id INT REFERENCES teams(id) ON DELETE CASCADE,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    PRIMARY KEY (team_id, user_id)
);

CREATE TABLE IF NOT EXISTS sessions (
    id         VARCHAR(64) PRIMARY KEY,
    user_id    INT REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    ip_address VARCHAR(45),
    user_agent TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id         SERIAL PRIMARY KEY,
    user_id    INT,
    action     VARCHAR(100),
    detail     TEXT,
    ip_address VARCHAR(45),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_permissions_parent ON permissions(parent_id);
CREATE INDEX IF NOT EXISTS idx_permissions_type ON permissions(resource_type);
CREATE INDEX IF NOT EXISTS idx_permissions_route ON permissions(route_pattern);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_user_roles_user ON user_roles(user_id);
CREATE INDEX IF NOT EXISTS idx_role_permissions_role ON role_permissions(role_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_created ON audit_log(created_at);
