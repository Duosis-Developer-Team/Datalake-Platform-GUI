# RBAC + LDAP Implementation

## Status (completed in development)

- [x] Dedicated `auth-db` PostgreSQL service with `auth_pgdata` volume (`docker-compose.yml`).
- [x] Auth schema + startup migration + seed (`sql/auth_schema.sql`, `src/auth/migration.py`, `src/auth/seed.py`).
- [x] Hierarchical permissions + catalog sync (`src/auth/permission_catalog.py`, `src/auth/registry.py`).
- [x] Permission resolution + section visibility (`src/auth/permission_service.py`).
- [x] Sessions, login/logout routes, middleware (`src/auth/routes.py`, `src/auth/middleware.py`).
- [x] LDAP service (`src/auth/ldap_service.py`).
- [x] Dash integration: login page, access denied, admin placeholders, settings auth placeholder (`app.py`, `src/pages/...`).
- [x] Sidebar: permission-filtered nav + sign out (`src/components/sidebar.py`).
- [x] DC View + Overview: section-level gating (`src/pages/dc_view.py`, `src/pages/home.py`).
- [x] Documentation (`docs/AUTH_SYSTEM.md`), `.env.example`, unit tests (`tests/test_permission_service.py`, `tests/test_crypto.py`).

## Follow-up (optional)

- Full CRUD UIs for users, roles matrix, permission tree editor, LDAP forms (currently placeholders).
- API-layer auth (FastAPI dependencies) for microservices.
- Redis-backed permission cache invalidation.
