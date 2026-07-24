# HMDL Configuration Screen (TASK-60)

**Date:** 2026-07-23
**Task:** TASK-60 "Datalake WebUI'a HMDL Configuration Ekranı" — Bulutistan / Zabbix L1 Support / HMDL (Netbox-Zabbix)
**Description (verbatim):** _"DL WebUI'da HMDL ile yapılan netbox-zabbix otomasyonunun konfigürasyonlarının yapılabileceği bir ekran eklenmeli."_

## Problem

The **HMDL netbox-zabbix automation** (`project-zabake/zabbix-netbox`, an Ansible role run from AWX/AAP) syncs NetBox ("Loki") + Datalake inventory into Zabbix hosts. Its configuration lives in three tiers:

- **Tier A — runtime variables** (`defaults/main.yml` + AWX Extra Vars/Survey): connection endpoints, source routing (`*_source: loki|datalake`), sync-scope toggles, execution mode (`dry_run`, `device_limit`, `location_filter`, parallel workers), SMTP, HMDL audit logging. ~50 variables.
- **Tier B — mapping YAML files** (`mappings/*.yml`, 10 files): device_type classification/filter, templates, tag derivation, host groups, datacenter→proxy. Git-versioned; AWX pulls them via SCM.
- **Tier C — audit DB** (`hmdl` schema, Postgres): sync history / diff logs — read-only.

Today there is **no way to configure this automation from the GUI**. The GUI (`Datalake-Platform-GUI`, a Plotly Dash app) already has **read-only** HMDL admin pages (`/administration/integrations/hmdl` → Overview / Sync Health / Coverage), fed by the in-repo `hmdl-api` microservice (FastAPI, port 8007, GET-only over Postgres). Config changes are done by hand: edit YAML → commit/push → AWX SCM pull, or via AWX Extra Vars/Survey. There is **no AWX API client anywhere** in the codebase.

## Goal

Add an Administration screen where an operator can configure and control the netbox-zabbix automation from the GUI. Delivered in **two phases**:

- **Phase 1 (this spec's core):** AWX **run & schedule control** for Tier A runtime variables — view/edit non-secret runtime config, trigger runs, view run/schedule status. Self-contained in `Datalake-Platform-GUI` (GUI page + `hmdl-api`).
- **Phase 2 (outlined here, own spec later):** Tier B mapping/taxonomy editor, git-backed.

Tier C is already surfaced read-only (Sync Health / recent runs) and is reused, not rebuilt.

## Where it lives

A new 4th tab under **Administration › Integrations › HMDL**:

- Route: `/administration/integrations/hmdl/config` — label **"Configuration"**.
- Sub-nav + dispatch use the existing settings-shell mechanics: add to `HMDL_TABS` and `_PAGE_BUILDERS` in `src/pages/settings/shell.py`, plus a new permission code.

## Phase 1 — AWX Run & Schedule Control (Tier A)

### What the screen does

1. **Show current state:** the netbox-zabbix AWX job template's current `extra_vars`, its schedule(s), and the last run status.
2. **Edit non-secret runtime variables** and Save:
   - Source routing: `device_source`, `platform_source`, `virtual_fw_source` (`loki|datalake`) — `dmc.Select`
   - Sync scope: `sync_devices`, `sync_platforms`, `sync_virtual_fws`, `report_izlenmeyecek`, `create_devices_disabled`, `create_platforms_disabled`, `create_virtual_fws_disabled` — `dmc.Switch`
   - Execution: `dry_run`, `only_fetch`, `debug_mode` (Switch); `device_limit`, `parallel_compare_workers` (`dmc.NumberInput`); `location_filter` (`dmc.TextInput`); `parallel_compare_ignore_errors` (Switch)
   - HMDL logging: `hmdl_log_enabled` — `dmc.Switch`
   - Email: `mail_recipients` (`dmc.TagsInput` / multi), `mail_from` (`dmc.TextInput`)
   - Connection endpoints (host/URL only, **no passwords**): `zabbix_url`, `netbox_url`, `discovery_db_host`, `discovery_db_port`, `discovery_db_name`
3. **Run now:** trigger the job template (optional `dry_run` override), display returned job id + poll status.
4. **Schedule:** show schedule(s) and enable/disable.

### Security boundary (non-negotiable)

Secrets — DB / Zabbix / NetBox passwords, NetBox token, SNMP community/passphrases — are **never displayed and never editable** in the UI. They remain in AWX Credentials / Vault (per ADR-0003). The UI only reads/writes non-secret "config as data". `hmdl-api` strips any secret-looking keys from responses and rejects them on write.

### Architecture & data flow

```
Browser (Dash page: src/pages/settings/integrations/hmdl_config.py)
  → src/services/api_client.py  (new wrappers: get_hmdl_awx_config / put_hmdl_awx_config /
                                 launch_hmdl_awx_job / get_hmdl_awx_job / get_hmdl_awx_schedules)
    → hmdl-api  (new router services/hmdl-api/app/routers/awx.py):
         GET  /api/v1/awx/config          → job template extra_vars (non-secret) + schedule summary + last run
         PUT  /api/v1/awx/config          → PATCH job template extra_vars (merge whitelisted keys)
         POST /api/v1/awx/launch          → launch job template (optional extra_vars override) → {job_id}
         GET  /api/v1/awx/jobs/{job_id}   → job status
         GET  /api/v1/awx/schedules       → schedule list
         PATCH/api/v1/awx/schedules/{id}  → enable/disable
      → services/hmdl-api/app/services/awx_client.py  (httpx; AWX_API_URL + AWX_TOKEN, server-side)
        → AWX REST /api/v2/job_templates/{id}/  (PATCH extra_vars) · /launch/ · /jobs/{id}/ · /schedules/
```

**Embedded decisions (approved):**
1. Config persists as the Job Template's **`extra_vars`** (every scheduled run uses it); "Run now" may override at launch.
2. Secrets excluded from the UI (above).
3. The AWX client lives **in `hmdl-api`** (token stays server-side; reusable by TASK-69's live control/staleness monitoring).

**Whitelist:** `hmdl-api` holds the allowed Tier-A key set (the fields listed above). `PUT /awx/config` merges only whitelisted keys into the JT's existing `extra_vars`; unknown/secret keys are rejected. `GET /awx/config` returns only whitelisted keys.

### Config / env (hmdl-api)

Add to `services/hmdl-api/app/config.py` (+ `docker-compose.yml`, `.env.example`):

- `AWX_API_URL` — e.g. `https://awx.example/api/v2` (default `""`)
- `AWX_TOKEN` — AWX personal access token (secret; default `""`)
- `AWX_NETBOX_ZABBIX_JT_ID` — job template id or name for the netbox-zabbix sync
- `AWX_VERIFY_SSL` — default `false`
- `AWX_ENABLED` — default `false`; when false (or URL/token missing) the API reports `awx_unavailable` instead of calling AWX

The operator generates the token from the AWX web UI (User → Tokens). Until it is provided, `AWX_ENABLED=false` and the screen shows a non-blocking "AWX not configured" banner; development/tests run against a mocked AWX client.

### Error handling

- AWX unreachable / disabled / misconfigured → `hmdl-api` returns a structured `{"awx_available": false, "reason": ...}` (HTTP 200 for the config GET so the page renders; 503 for launch/write attempts). GUI shows an informative banner, not a stack trace.
- Secrets never returned; write of a non-whitelisted key → 400.
- All Dash callbacks wrapped `try/except` → `dmc.Alert` (green success / red failure), mirroring `crm_thresholds.py`.

### Permission wiring

- New code `page:settings_hmdl_config`, added to `src/auth/permission_catalog.py` under the HMDL integrations group (sibling of `page:settings_hmdl_overview`).
- Added to `HMDL_TABS` and `_PAGE_BUILDERS` in `src/pages/settings/shell.py`; the shell gates the sub-page via `can_view(user_id, code)`.
- If `resolve_pathname_to_page_code` needs an explicit branch for the admin path, add it in `src/auth/permission_service.py` (verify during implementation).

### Files touched (Phase 1)

**GUI:**
- `src/pages/settings/integrations/hmdl_config.py` (new) — page `build_layout(search=None)` + Save / Run-now / poll callbacks (model on `crm_thresholds.py`).
- `src/pages/settings/shell.py` — import page, add to `HMDL_TABS` + `_PAGE_BUILDERS`.
- `src/auth/permission_catalog.py` — new `page:settings_hmdl_config` node.
- `src/auth/permission_service.py` — resolver branch if required.
- `src/services/api_client.py` — new AWX wrappers (`_get_client_hmdl()` reused).

**hmdl-api:**
- `app/routers/awx.py` (new) — the routes above; registered in `app/main.py`.
- `app/services/awx_client.py` (new) — httpx client + whitelist/secret-strip logic.
- `app/models/schemas.py` — request/response models.
- `app/config.py` — AWX settings.
- `docker-compose.yml`, `.env.example` — env wiring.

### Testing

- **hmdl-api:** `awx_client` unit tests with mocked httpx (config get/patch, launch, job status, schedule); whitelist enforcement + secret-strip; `AWX_ENABLED=false` path. Router tests with the client mocked.
- **GUI:** `api_client` wrapper tests (mocked httpx); `hmdl_config.build_layout` render test; Save callback happy/error; "AWX unavailable" banner render.
- Run with the main checkout's `.venv` / Python 3.11 (system `python3` is 3.9 and mis-parses `X | Y` type hints).

## Phase 2 — Mapping / Taxonomy Editor (Tier B, git-backed) — outline

Own spec later. Sketch:

- GUI editor pages for `netbox_device_type_mapping.yml`, `tags_config.yml`, `host_groups_config.yml` (and later `templates.yml`), following `README_CONFIG.md` semantics (source types, dot-path, fallback, priority).
- Save → `hmdl-api` git-write service: clone/pull `project-zabake`, edit `mappings/*.yml`, validate against schema, commit, push; AWX SCM picks up on next run. "Sync + run" reuses the Phase 1 AWX client.
- **Dependencies:** git push access + target repo/branch/credentials (note: existing push constraints on `.github/workflows/*`; general push access must be confirmed).

## Open dependencies (to confirm before go-live, not blocking build)

1. AWX base URL, API token, and the netbox-zabbix job template id/name; network reachability from the `hmdl-api` container.
2. Phase 2: git push access to `project-zabake` and the branch/credentials the write service uses.

## Non-goals

- Editing secrets in the UI (stay in AWX Credentials / Vault).
- Rebuilding read-only views (Overview / Sync Health / Coverage already exist).
- Phase 2 mapping editor (separate spec).
