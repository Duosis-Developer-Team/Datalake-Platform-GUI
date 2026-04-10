# Authentication and RBAC System

This document describes the reusable authentication stack used by the Datalake Platform GUI: dedicated **Auth DB**, **hierarchical permissions**, **LDAP** integration, and **Flask/Dash** session handling.

## Overview

- **Auth database**: Separate PostgreSQL instance (`auth-db` in Docker Compose) with persistent volume `auth_pgdata`.
- **Schema**: `users`, `roles`, `permissions` (tree via `parent_id`), `role_permissions`, `user_roles`, `sessions`, `ldap_config`, `ldap_group_role_mapping`, `teams`, `team_members`, `audit_log`, `schema_migrations`.
- **Permission model**: Tree of nodes (`page_group` → `page` → `section` → `sub_section` → `action`). Effective rights resolve upward (inheritance) with explicit `role_permissions` rows.
- **Runtime**: `src/auth/migration.py` applies DDL on startup; `src/auth/seed.py` seeds roles and default grants; `src/auth/registry.py` syncs the static catalog from `src/auth/permission_catalog.py`.
- **HTTP**: Flask blueprint `src/auth/routes.py` (`/auth/login`, `/auth/logout`), cookie-backed sessions stored in `sessions` table.
- **UI**: Dash `render_main_content` enforces `page:*` access; section-level visibility uses `get_visible_sections()` for nested `sec:` / `sub:` / `action:` codes.

## Environment variables

See [`.env.example`](../.env.example) for `AUTH_*`, `SECRET_KEY`, `FERNET_KEY`, `AUTH_DISABLED`, etc.

## Key modules

| Module | Responsibility |
|--------|----------------|
| `src/auth/config.py` | Env configuration |
| `src/auth/db.py` | Auth DB connection pool |
| `src/auth/crypto.py` | Password hashing, Fernet encryption, session tokens |
| `src/auth/migration.py` | Startup DDL |
| `src/auth/seed.py` | Default roles, grants, admin user |
| `src/auth/registry.py` | Sync catalog → DB |
| `src/auth/permission_catalog.py` | Default permission tree |
| `src/auth/permission_service.py` | Resolve path → page code, effective triplets, visible sections |
| `src/auth/service.py` | Sessions, users |
| `src/auth/ldap_service.py` | LDAP bind, group listing, group→role mapping |
| `src/auth/middleware.py` | `before_request` gate |
| `src/auth/routes.py` | Login/logout routes |

## Docker

```bash
docker compose up -d auth-db app
```

`app` waits for `auth-db` healthcheck. Data survives container removal via named volume.

## Reusing in another application

1. Copy `src/auth/` and `sql/auth_schema.sql`.
2. Point `AUTH_DB_*` to your PostgreSQL instance.
3. Call `run_migrations()` and `seed_all()` (or your own seed) at startup.
4. Register `auth_bp` and `register_middleware(app)` on the Flask `server`.
5. Define your page/section tree in `permission_catalog.py` (or DB-only dynamic nodes).
6. Enforce `can_view` / `get_visible_sections` in your router layer.

## Security notes

- Never commit production LDAP credentials; configure via UI or secrets.
- Set strong `SECRET_KEY` and `FERNET_KEY` in production.
- Replace open CORS on APIs when exposing beyond trusted networks.

## Troubleshooting

- **Connection refused to Auth DB**: Ensure `auth-db` is running and `AUTH_DB_HOST`/`AUTH_DB_PORT` match (default host port `5433`).
- **Import errors**: `pip install -r requirements.txt` (includes `ldap3`, `cryptography`, `pydantic`).
