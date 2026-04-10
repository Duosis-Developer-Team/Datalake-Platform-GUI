# RBAC + LDAP Implementation

## Status (completed in development)

- [x] Dedicated `auth-db` PostgreSQL service with `auth_pgdata` volume (`docker-compose.yml`).
- [x] Auth schema + startup migration v1/v2 (`sql/auth_schema.sql`, `src/auth/migration.py`) — v2 renames legacy `page:admin_*` → `page:settings_*`.
- [x] Hierarchical permissions + catalog sync (`src/auth/permission_catalog.py`, `src/auth/registry.py`).
- [x] Permission resolution + section visibility + in-process + optional Redis cache (`src/auth/permission_service.py`).
- [x] Sessions, login/logout, Settings POST actions (`src/auth/routes.py`, `src/auth/middleware.py`).
- [x] LDAP service + `LDAPException` import fix (`src/auth/ldap_service.py`).
- [x] Settings UI: `/settings/*` tab shell, CRUD helpers (`src/pages/settings/`, `src/auth/settings_crud.py`).
- [x] JWT for Dash → microservices (`src/auth/api_jwt.py`, `src/services/api_client.py`); FastAPI optional auth (`services/*/app/core/api_auth.py`, `API_AUTH_REQUIRED`).
- [x] Sidebar: single Settings link + sign out (`src/components/sidebar.py`).
- [x] Section gating: DC View, Overview, Global View, Data Centers, DC Detail, Customer View (export), Query Explorer (tabs/export).
- [x] Documentation (`docs/AUTH_SYSTEM.md`), `.env.example`, `k8s/auth-secrets-reference.yaml`.
- [x] Unit tests: `tests/test_*` (permission, crypto, api_jwt, auth_service, migration, registry, ldap_service).

## Follow-up (optional)

- Role matrix UI: extend beyond first 100 permission nodes if the tree grows larger.
- Hierarchical permission tree editor (visual inherited vs explicit) instead of flat table.
- LDAP connection test endpoint and richer validation.
