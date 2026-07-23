# TASK-64 — Application Versioning Panel (Uygulama versiyonlaması paneli)

**Date:** 2026-07-23
**Repo:** Datalake-Platform-GUI
**Branch:** worktree-task-64-version-panel
**Status:** Design approved, pending spec review

## Problem

The Datalake Platform has shipped continuously since its first release (2026-02-19,
625 commits) but there is **no record of what was deployed, when, or what changed**.
There are no git tags, no CHANGELOG, no `APP_VERSION` constant. Under Administration
we need a panel that shows the platform's deployed versions from first release to today
with their changelog contents, and every new deployment must contribute its own version
+ changelog entry going forward.

## Goals

1. **Backward-looking:** Reconstruct a version history from the existing git log and
   show it in Administration, newest first, with per-version change lists.
2. **Forward-looking:** Every new deployment automatically records its version and
   which services came up when — no manual entry required.
3. **Platform version + service detail:** The main list is a single platform version
   (CalVer, e.g. `2026.07.3`); expanding a version reveals which service reported which
   image/SHA and when it started.

## Non-Goals (YAGNI)

- No rollback / deploy-trigger actions from the panel. Read-only display.
- No editing of changelog text through the UI in v1 (backfill is script-generated;
  hand-curation, if ever needed, is a later iteration).
- No cross-repo aggregation. Only the five images this repo builds
  (frontend, customer-api, datacenter-api, query-api, chatbot-api) plus admin-api.
- No real-time push. Panel reads current DB state on page load.

## Architecture Overview

Follows the existing Administration pattern exactly (see `iam/audit.py` +
`admin-api/routers/audit.py` + `admin_client.py`):

```
                          ┌───────────────────────────────────┐
  git log (one-time)  ──▶ │ backfill script                   │
                          │ scripts/backfill_platform_versions │
                          └──────────────┬────────────────────┘
                                         │ writes
                                         ▼
   service startup ──POST──▶ admin-api  ┌──────────────────────┐
   (self-register)          /versions   │  auth DB (Postgres)   │
                            router  ───▶ │  platform_releases    │
                                         │  release_changes      │
   GUI page  ◀──admin_client──GET────── │  service_deployments  │
   /administration/platform/versions    └──────────────────────┘
```

### Data model (3 tables, new migration `003_platform_versions.sql`, schema version 4)

**`platform_releases`** — one row per platform version (the changelog headline)
| column | type | notes |
|---|---|---|
| `id` | serial PK | |
| `version` | text unique | CalVer, e.g. `2026.07.3` |
| `released_at` | date | representative date of the version window |
| `title` | text null | optional human title |
| `notes` | text null | optional summary |
| `source` | text | `backfill` \| `deploy` — how the row was created |
| `created_at` | timestamptz default now() | |

**`release_changes`** — individual change items belonging to a release
| column | type | notes |
|---|---|---|
| `id` | serial PK | |
| `release_id` | int FK → platform_releases(id) on delete cascade | |
| `change_type` | text | `feat` \| `fix` \| `perf` \| `chore` \| `docs` \| `refactor` \| `other` |
| `summary` | text | commit subject, cleaned of the conventional-commit prefix |
| `commit_sha` | text null | short SHA for traceability |
| `scope` | text null | conventional-commit scope, e.g. `gui`, `crm` |

**`service_deployments`** — raw deploy events, one row per service startup
| column | type | notes |
|---|---|---|
| `id` | serial PK | |
| `service` | text | `frontend` \| `customer-api` \| `datacenter-api` \| `query-api` \| `chatbot-api` \| `admin-api` |
| `version` | text | CalVer or `local`/SHA when no release assigned |
| `git_sha` | text null | short SHA baked into the image |
| `image_tag` | text null | e.g. `${GITHUB_SHA}` |
| `environment` | text | `production` \| `local` (from env) |
| `started_at` | timestamptz default now() | |

Indexes: `service_deployments(started_at desc)`, `service_deployments(version)`,
`release_changes(release_id)`, unique on `platform_releases(version)`.

**Relationship:** `service_deployments.version` joins to `platform_releases.version`
by string. A deployment whose version has no release row still records (shows as an
un-annotated current deployment); its release notes can be backfilled/added later.
"Currently live" = the version of the most recent `service_deployments` row per
service; the release carrying the newest deployment gets the **live** badge.

### admin-api: new `versions` router

`services/admin-api/app/routers/versions.py`, registered in `main.py` under
`/api/v1` with the existing `verify_api_user` dependency. Endpoints:

- `GET /api/v1/versions` → list releases (newest first) each with its nested
  `changes[]` and the set of services/deployments reported for that version.
- `GET /api/v1/versions/current` → the version(s) live now, per service.
- `POST /api/v1/versions/deployments` → **self-registration**. Body:
  `{service, version, git_sha, image_tag, environment}`. Idempotent-ish: inserts a
  new deployment row on each startup (a restart is a legitimate new event; dedup is
  not required for v1). This is the endpoint each service calls on boot.

Pydantic models added to `services/admin-api/app/models.py`
(`ReleaseOut`, `ReleaseChangeOut`, `ServiceDeploymentOut`, `RegisterDeploymentRequest`).

### GUI client + page

- `src/services/admin_client.py`: add `list_platform_releases()`,
  `get_current_versions()`, `register_deployment(...)` mirroring the existing
  API/local-fallback shape. Local fallback reads the same auth DB directly via a new
  small `src/auth/versions_crud.py` (mirrors `settings_crud` style) so single-service
  local dev works without admin-api.
- `src/pages/settings/platform/versions.py`: `build_layout(search)` renders the
  timeline using `settings_page_shell`, `section_header`, `relative_time` from
  `ui_tokens` (same helpers `audit.py` uses). Newest release on top with a green
  **Live** badge; each release shows date, change list (feat/fix/perf shown, others
  collapsed as "+N technical changes"), and an expandable service-detail block
  (service · version · SHA · started_at).

### Navigation + permissions

- New top-level Administration tab **Platform** (4th, after Overview / Identity &
  Access / Integration and Configuration) in `src/pages/settings/shell.py`. New
  `PLATFORM_TABS` list with one entry: `Versions` →
  `/administration/platform/versions`, permission `page:settings_platform_versions`.
- `_PAGE_BUILDERS`, `_section_for_path` ("platform"), `_top_nav`, `_sub_nav`,
  `has_any_settings_access`, and a `first_allowed_platform_path` helper updated to
  include the new section, matching how IAM/Integrations are wired.
- `src/auth/permission_catalog.py`: add
  `_n("page:settings_platform_versions", "Platform Versions", "config",
  route_pattern="/administration/platform/versions", sort_order=80)` under
  `settings_grp`. Idempotent auth migrations already `INSERT ... ON CONFLICT DO
  NOTHING` the catalog, so the new permission code is seeded on next boot.

### Backfill script

`scripts/backfill_platform_versions.py`:
1. Reads `git log --pretty` from the repo (first commit → HEAD).
2. Buckets commits into **weekly** windows; each week that has commits becomes a
   release `YYYY.MM.N` where N is the running per-month sequence.
3. Parses conventional-commit prefixes (`feat`, `fix`, `perf`, `chore`, `docs`,
   `refactor`; anything else → `other`) into `release_changes`. `feat`/`fix`/`perf`
   are surfaced in the UI; the rest are counted.
4. Upserts into `platform_releases`/`release_changes` with `source='backfill'`
   (idempotent on `version`; re-runnable). Does not touch `service_deployments`.

Run once manually (documented in the script docstring). No DB writes happen at import.

### Self-registration on startup

Each service, on boot, POSTs its identity to admin-api once:
- **Version source:** image env vars baked at build time — `APP_VERSION` (CalVer),
  `GIT_SHA`, `IMAGE_TAG`, `DEPLOY_ENV`. The frontend already has `APP_BUILD_ID`
  (short SHA) wired through the root Dockerfile + docker-compose; reuse/extend that.
  Backend service Dockerfiles gain `ARG APP_VERSION/GIT_SHA` → `ENV`, and CI
  (`.github/workflows/main.yml`) passes `--build-arg GIT_SHA=${GITHUB_SHA}` (and an
  `APP_VERSION` it derives) to each `docker buildx build`.
- **Frontend** (`app.py`): a guarded startup call (best-effort, swallowed on failure)
  that invokes `admin_client.register_deployment("frontend", ...)`.
- **Backend services** (customer-api, datacenter-api, query-api, chatbot-api,
  admin-api): a small shared helper called in each FastAPI `lifespan` startup that
  POSTs to admin-api (`admin-api` registers itself directly against its own DB).
- **Failure is non-fatal:** registration is wrapped so a missing/unreachable admin-api
  never blocks a service from starting (same tolerance as the existing migration
  try/except in `admin-api/main.py`).

## Build Sequence (for the implementation plan)

1. **DB migration** — `sql/migrations/003_platform_versions.sql` + schema-version-4
   block in `src/auth/auth_db_migrations.py`. Verify tables created idempotently.
2. **admin-api router + models** — `versions.py`, models, register in `main.py`.
   Unit tests for the three endpoints.
3. **GUI client + local CRUD** — `versions_crud.py` + `admin_client` methods with
   API/local fallback. Tests for the local path.
4. **GUI page + nav + permission** — `platform/versions.py`, `shell.py` wiring,
   `permission_catalog.py` entry. Redirect test parity with existing admin routes.
5. **Backfill script** — `scripts/backfill_platform_versions.py`; run once, verify
   the panel shows the reconstructed history.
6. **Self-registration** — Dockerfile build args, CI build-args, per-service startup
   hook, docker-compose env wiring. Verify a fresh deploy inserts a
   `service_deployments` row and the panel marks it live.

## Testing Strategy

- **Migration:** idempotency test — run twice, tables + schema_migrations row stable.
- **admin-api:** endpoint tests (list/current/register) against a test DB, following
  `services/admin-api/tests` style.
- **Backfill:** parse-and-bucket unit test on a fixed synthetic git-log sample →
  deterministic releases/changes; assert weekly bucketing + prefix parsing.
- **GUI:** `build_layout` renders without error given a mocked client payload
  (empty history + populated history); nav shows the Platform tab only with the
  permission. Extend `tests/test_administration_redirects.py` coverage for the new
  route.
- **Self-registration:** helper posts the expected body and swallows connection
  errors (mocked httpx) without raising.

## Risks / Open Questions

- **Backfill fidelity:** commit dates ≠ real deploy dates (the honest limitation the
  user accepted). Weekly buckets are an approximation of release cadence, labeled
  clearly as reconstructed history (`source='backfill'`).
- **Version derivation for CI:** `APP_VERSION` for forward deploys needs a rule
  (e.g. current `YYYY.MM.N`). v1 can start each real deploy at the next CalVer after
  the last backfilled week; exact CI derivation finalized in step 6.
- **Service Dockerfiles** currently lack build args; step 6 adds them uniformly.
