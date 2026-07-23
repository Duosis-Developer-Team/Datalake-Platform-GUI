# HMDL Configuration Screen — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an Administration screen (`/administration/integrations/hmdl/config`) that lets an operator view/edit the netbox-zabbix AWX job template's non-secret runtime variables, trigger runs, and view/toggle schedules — backed by a new AWX client in the `hmdl-api` microservice.

**Architecture:** GUI Dash page → `src/services/api_client.py` wrappers → new `hmdl-api` router `/api/v1/awx/*` → new `hmdl-api` `awx_client` (httpx) → AWX REST `/api/v2/...`. The AWX token stays server-side in `hmdl-api`. Config is stored as the Job Template's `extra_vars`. Secrets are never read or written by the UI.

**Tech Stack:** Python 3.11, FastAPI + httpx + PyYAML (hmdl-api), Plotly Dash + dash-mantine-components 0.14.1 (GUI), pytest.

## Global Constraints

- **Test interpreter (`PY`):** `/Users/namlisarac/Desktop/Work/Datalake/Datalake-Platform-GUI/.venv/bin/python` (Python 3.11.15; system `python3` is 3.9 and mis-parses `X | Y` hints — never use it).
- **Run GUI tests** from the worktree root: `$PY -m pytest tests/<file> -v`.
- **Run hmdl-api tests** from the service dir: `cd services/hmdl-api && $PY -m pytest tests/<file> -v`.
- **Commit trailer** (every commit): end the message with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **Secrets boundary:** the UI and the `/awx/config` GET/PUT must never return or accept keys matching secret hints (`password`, `passwd`, `secret`, `token`, `passphrase`, `community`, `_pass`). Only the whitelisted Tier-A keys are read/written.
- **Whitelisted Tier-A keys** (the single source of truth, defined in Task 1 as `ALLOWED_EXTRA_VARS`): `device_source`, `platform_source`, `virtual_fw_source`, `sync_devices`, `sync_platforms`, `sync_virtual_fws`, `report_izlenmeyecek`, `create_devices_disabled`, `create_platforms_disabled`, `create_virtual_fws_disabled`, `dry_run`, `only_fetch`, `debug_mode`, `device_limit`, `parallel_compare_workers`, `parallel_compare_ignore_errors`, `location_filter`, `hmdl_log_enabled`, `mail_recipients`, `mail_from`, `zabbix_url`, `netbox_url`, `discovery_db_host`, `discovery_db_port`, `discovery_db_name`.
- **Component library:** dash-mantine-components (`import dash_mantine_components as dmc`); `dash_bootstrap_components` is NOT used.
- Do not push; commits stay on branch `worktree-task-60-hmdl-config`.

---

### Task 1: AWX settings + client scaffolding (config, is_configured, whitelist filter)

**Files:**
- Modify: `services/hmdl-api/app/config.py` (add AWX settings after `api_jwt_secret`)
- Create: `services/hmdl-api/app/services/awx_client.py`
- Test: `services/hmdl-api/tests/test_awx_client.py`

**Interfaces:**
- Consumes: `app.config.settings`
- Produces:
  - `ALLOWED_EXTRA_VARS: set[str]`
  - `class AwxUnavailable(RuntimeError)`
  - `is_configured() -> bool`
  - `is_secret_key(key: str) -> bool`
  - `filter_allowed(data: dict) -> dict`
  - `_client() -> httpx.Client`  (raises `AwxUnavailable` when not configured)

- [ ] **Step 1: Write the failing test**

Create `services/hmdl-api/tests/test_awx_client.py`:

```python
"""Unit tests for the hmdl-api AWX client helpers."""

from app.config import settings
from app.services import awx_client


def test_is_configured_false_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "awx_enabled", False)
    monkeypatch.setattr(settings, "awx_api_url", "https://awx/api/v2")
    monkeypatch.setattr(settings, "awx_token", "tok")
    monkeypatch.setattr(settings, "awx_netbox_zabbix_jt_id", "42")
    assert awx_client.is_configured() is False


def test_is_configured_true_when_all_present(monkeypatch):
    monkeypatch.setattr(settings, "awx_enabled", True)
    monkeypatch.setattr(settings, "awx_api_url", "https://awx/api/v2")
    monkeypatch.setattr(settings, "awx_token", "tok")
    monkeypatch.setattr(settings, "awx_netbox_zabbix_jt_id", "42")
    assert awx_client.is_configured() is True


def test_filter_allowed_keeps_whitelist_drops_unknown_and_secrets():
    raw = {
        "dry_run": True,
        "device_limit": 5,
        "zabbix_url": "https://z/api_jsonrpc.php",
        "zabbix_password": "hunter2",   # secret -> dropped
        "netbox_token": "abc",          # secret -> dropped
        "totally_unknown": "x",         # not whitelisted -> dropped
    }
    out = awx_client.filter_allowed(raw)
    assert out == {"dry_run": True, "device_limit": 5, "zabbix_url": "https://z/api_jsonrpc.php"}


def test_is_secret_key():
    assert awx_client.is_secret_key("zabbix_password") is True
    assert awx_client.is_secret_key("netbox_token") is True
    assert awx_client.is_secret_key("discovery_db_password") is True
    assert awx_client.is_secret_key("device_source") is False


def test_client_raises_when_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "awx_enabled", False)
    try:
        awx_client._client()
        assert False, "expected AwxUnavailable"
    except awx_client.AwxUnavailable:
        pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/hmdl-api && $PY -m pytest tests/test_awx_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.awx_client'` (and `settings` has no `awx_*` attrs).

- [ ] **Step 3: Add AWX settings to `config.py`**

In `services/hmdl-api/app/config.py`, add inside `class Settings` right after the `api_jwt_secret` line:

```python
    awx_enabled: bool = _env("AWX_ENABLED", default="false").lower() in ("1", "true", "yes")
    awx_api_url: str = _env("AWX_API_URL", default="")
    awx_token: str = _env("AWX_TOKEN", default="")
    awx_netbox_zabbix_jt_id: str = _env("AWX_NETBOX_ZABBIX_JT_ID", default="")
    awx_verify_ssl: bool = _env("AWX_VERIFY_SSL", default="false").lower() in ("1", "true", "yes")
```

- [ ] **Step 4: Create `awx_client.py` (scaffolding only)**

Create `services/hmdl-api/app/services/awx_client.py`:

```python
"""AWX REST client for the netbox-zabbix job template (server-side, hmdl-api).

Only non-secret Tier-A runtime variables are read/written. Secrets stay in
AWX Credentials / Vault and are never returned or accepted here.
"""

from __future__ import annotations

import json
import logging

import httpx
import yaml

from app.config import settings

logger = logging.getLogger(__name__)

ALLOWED_EXTRA_VARS: set[str] = {
    "device_source", "platform_source", "virtual_fw_source",
    "sync_devices", "sync_platforms", "sync_virtual_fws",
    "report_izlenmeyecek",
    "create_devices_disabled", "create_platforms_disabled", "create_virtual_fws_disabled",
    "dry_run", "only_fetch", "debug_mode",
    "device_limit", "parallel_compare_workers", "parallel_compare_ignore_errors",
    "location_filter",
    "hmdl_log_enabled",
    "mail_recipients", "mail_from",
    "zabbix_url", "netbox_url",
    "discovery_db_host", "discovery_db_port", "discovery_db_name",
}

_SECRET_HINTS = ("password", "passwd", "secret", "token", "passphrase", "community", "_pass")


class AwxUnavailable(RuntimeError):
    """Raised when AWX is not configured or unreachable."""


def is_configured() -> bool:
    return bool(
        settings.awx_enabled
        and settings.awx_api_url
        and settings.awx_token
        and settings.awx_netbox_zabbix_jt_id
    )


def is_secret_key(key: str) -> bool:
    lk = (key or "").lower()
    return any(hint in lk for hint in _SECRET_HINTS)


def filter_allowed(data: dict) -> dict:
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if k in ALLOWED_EXTRA_VARS and not is_secret_key(k)}


def _parse_extra_vars(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = yaml.safe_load(raw)  # AWX stores extra_vars as a YAML/JSON string
        return parsed if isinstance(parsed, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _client() -> httpx.Client:
    if not is_configured():
        raise AwxUnavailable("AWX is not configured")
    return httpx.Client(
        base_url=settings.awx_api_url.rstrip("/"),
        headers={
            "Authorization": f"Bearer {settings.awx_token}",
            "Content-Type": "application/json",
        },
        timeout=30.0,
        verify=settings.awx_verify_ssl,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd services/hmdl-api && $PY -m pytest tests/test_awx_client.py -v`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add services/hmdl-api/app/config.py services/hmdl-api/app/services/awx_client.py services/hmdl-api/tests/test_awx_client.py
git commit -m "feat(hmdl-api): AWX settings + client scaffolding with Tier-A whitelist

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: AWX client read methods (get_extra_vars, get_job, list_schedules)

**Files:**
- Modify: `services/hmdl-api/app/services/awx_client.py`
- Test: `services/hmdl-api/tests/test_awx_client_read.py`

**Interfaces:**
- Consumes: `_client()`, `filter_allowed()`, `_parse_extra_vars()` (Task 1)
- Produces:
  - `get_extra_vars() -> dict`
  - `get_job(job_id: int) -> dict`  → `{"job_id", "status", "started", "finished", "failed"}`
  - `list_schedules() -> list[dict]`  → each `{"id", "name", "enabled", "next_run", "rrule"}`

- [ ] **Step 1: Write the failing test**

Create `services/hmdl-api/tests/test_awx_client_read.py`:

```python
"""Read-path tests for awx_client using a mocked httpx.Client."""

from unittest.mock import MagicMock, patch

from app.services import awx_client


def _fake_client_cm(mock_client):
    cm = MagicMock()
    cm.__enter__.return_value = mock_client
    cm.__exit__.return_value = False
    return cm


def test_get_extra_vars_parses_and_filters():
    mock_client = MagicMock()
    resp = MagicMock()
    resp.json.return_value = {
        "extra_vars": "dry_run: true\ndevice_limit: 10\nzabbix_password: secret\n"
    }
    mock_client.get.return_value = resp
    with patch.object(awx_client, "_client", return_value=_fake_client_cm(mock_client)):
        out = awx_client.get_extra_vars()
    assert out == {"dry_run": True, "device_limit": 10}


def test_get_job_normalizes_fields():
    mock_client = MagicMock()
    resp = MagicMock()
    resp.json.return_value = {
        "id": 77, "status": "successful", "started": "t1", "finished": "t2", "failed": False,
    }
    mock_client.get.return_value = resp
    with patch.object(awx_client, "_client", return_value=_fake_client_cm(mock_client)):
        out = awx_client.get_job(77)
    assert out == {"job_id": 77, "status": "successful", "started": "t1", "finished": "t2", "failed": False}


def test_list_schedules_shapes_rows():
    mock_client = MagicMock()
    resp = MagicMock()
    resp.json.return_value = {"results": [
        {"id": 3, "name": "nightly", "enabled": True, "next_run": "t", "rrule": "FREQ=DAILY", "extra": "x"},
    ]}
    mock_client.get.return_value = resp
    with patch.object(awx_client, "_client", return_value=_fake_client_cm(mock_client)):
        out = awx_client.list_schedules()
    assert out == [{"id": 3, "name": "nightly", "enabled": True, "next_run": "t", "rrule": "FREQ=DAILY"}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/hmdl-api && $PY -m pytest tests/test_awx_client_read.py -v`
Expected: FAIL — `AttributeError: module 'app.services.awx_client' has no attribute 'get_extra_vars'`.

- [ ] **Step 3: Add read methods to `awx_client.py`**

Append to `services/hmdl-api/app/services/awx_client.py`:

```python
def _jt_path() -> str:
    return f"/job_templates/{settings.awx_netbox_zabbix_jt_id}/"


def get_extra_vars() -> dict:
    with _client() as c:
        resp = c.get(_jt_path())
        resp.raise_for_status()
        jt = resp.json()
    return filter_allowed(_parse_extra_vars(jt.get("extra_vars")))


def get_job(job_id: int) -> dict:
    with _client() as c:
        resp = c.get(f"/jobs/{int(job_id)}/")
        resp.raise_for_status()
        j = resp.json()
    return {
        "job_id": j.get("id"),
        "status": j.get("status"),
        "started": j.get("started"),
        "finished": j.get("finished"),
        "failed": bool(j.get("failed")),
    }


def list_schedules() -> list[dict]:
    with _client() as c:
        resp = c.get(f"{_jt_path()}schedules/")
        resp.raise_for_status()
        results = resp.json().get("results", []) or []
    return [
        {
            "id": s.get("id"),
            "name": s.get("name"),
            "enabled": bool(s.get("enabled")),
            "next_run": s.get("next_run"),
            "rrule": s.get("rrule"),
        }
        for s in results
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd services/hmdl-api && $PY -m pytest tests/test_awx_client_read.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add services/hmdl-api/app/services/awx_client.py services/hmdl-api/tests/test_awx_client_read.py
git commit -m "feat(hmdl-api): AWX client read methods (extra_vars, job, schedules)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: AWX client write methods (patch_extra_vars, launch, set_schedule_enabled)

**Files:**
- Modify: `services/hmdl-api/app/services/awx_client.py`
- Test: `services/hmdl-api/tests/test_awx_client_write.py`

**Interfaces:**
- Consumes: `_client()`, `_jt_path()`, `filter_allowed()`, `_parse_extra_vars()`
- Produces:
  - `patch_extra_vars(updates: dict) -> dict`  (merges only whitelisted keys into current, PATCHes JT, returns new filtered dict)
  - `launch(extra_vars: dict | None = None) -> int`  (returns job id)
  - `set_schedule_enabled(schedule_id: int, enabled: bool) -> dict`  → `{"id", "enabled"}`

- [ ] **Step 1: Write the failing test**

Create `services/hmdl-api/tests/test_awx_client_write.py`:

```python
"""Write-path tests for awx_client using a mocked httpx.Client."""

import json
from unittest.mock import MagicMock, patch

from app.services import awx_client


def _fake_client_cm(mock_client):
    cm = MagicMock()
    cm.__enter__.return_value = mock_client
    cm.__exit__.return_value = False
    return cm


def test_patch_extra_vars_merges_whitelist_only():
    mock_client = MagicMock()
    get_resp = MagicMock()
    get_resp.json.return_value = {"extra_vars": "dry_run: false\nlocation_filter: DC13\n"}
    patch_resp = MagicMock()
    patch_resp.json.return_value = {"extra_vars": "dry_run: true\nlocation_filter: DC13\n"}
    mock_client.get.return_value = get_resp
    mock_client.patch.return_value = patch_resp
    with patch.object(awx_client, "_client", return_value=_fake_client_cm(mock_client)):
        out = awx_client.patch_extra_vars({"dry_run": True, "netbox_token": "leak", "bogus": 1})
    # secret + unknown dropped; result reflects merged JT state
    assert out == {"dry_run": True, "location_filter": "DC13"}
    # the PATCH body merged onto current and serialized as a JSON string
    sent = mock_client.patch.call_args.kwargs["json"]["extra_vars"]
    merged = json.loads(sent)
    assert merged["dry_run"] is True
    assert merged["location_filter"] == "DC13"
    assert "netbox_token" not in merged and "bogus" not in merged


def test_launch_returns_job_id():
    mock_client = MagicMock()
    resp = MagicMock()
    resp.json.return_value = {"job": 501, "id": 999}
    mock_client.post.return_value = resp
    with patch.object(awx_client, "_client", return_value=_fake_client_cm(mock_client)):
        job_id = awx_client.launch({"dry_run": True})
    assert job_id == 501
    body = mock_client.post.call_args.kwargs["json"]
    assert body["extra_vars"] == {"dry_run": True}


def test_set_schedule_enabled():
    mock_client = MagicMock()
    resp = MagicMock()
    resp.json.return_value = {"id": 3, "enabled": False}
    mock_client.patch.return_value = resp
    with patch.object(awx_client, "_client", return_value=_fake_client_cm(mock_client)):
        out = awx_client.set_schedule_enabled(3, False)
    assert out == {"id": 3, "enabled": False}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/hmdl-api && $PY -m pytest tests/test_awx_client_write.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'patch_extra_vars'`.

- [ ] **Step 3: Add write methods to `awx_client.py`**

Append to `services/hmdl-api/app/services/awx_client.py`:

```python
def patch_extra_vars(updates: dict) -> dict:
    clean = filter_allowed(updates)
    with _client() as c:
        get_resp = c.get(_jt_path())
        get_resp.raise_for_status()
        current = _parse_extra_vars(get_resp.json().get("extra_vars"))
        current.update(clean)
        patch_resp = c.patch(_jt_path(), json={"extra_vars": json.dumps(current)})
        patch_resp.raise_for_status()
        new = _parse_extra_vars(patch_resp.json().get("extra_vars"))
    return filter_allowed(new)


def launch(extra_vars: dict | None = None) -> int:
    body: dict = {}
    if extra_vars:
        body["extra_vars"] = filter_allowed(extra_vars)
    with _client() as c:
        resp = c.post(f"{_jt_path()}launch/", json=body)
        resp.raise_for_status()
        data = resp.json()
    job_id = data.get("job") or data.get("id")
    return int(job_id)


def set_schedule_enabled(schedule_id: int, enabled: bool) -> dict:
    with _client() as c:
        resp = c.patch(f"/schedules/{int(schedule_id)}/", json={"enabled": bool(enabled)})
        resp.raise_for_status()
        s = resp.json()
    return {"id": s.get("id"), "enabled": bool(s.get("enabled"))}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd services/hmdl-api && $PY -m pytest tests/test_awx_client_write.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add services/hmdl-api/app/services/awx_client.py services/hmdl-api/tests/test_awx_client_write.py
git commit -m "feat(hmdl-api): AWX client write methods (patch extra_vars, launch, schedule toggle)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: AWX router + main.py wiring

**Files:**
- Create: `services/hmdl-api/app/routers/awx.py`
- Modify: `services/hmdl-api/app/main.py` (import + include_router)
- Test: `services/hmdl-api/tests/test_awx_api.py`

**Interfaces:**
- Consumes: `app.services.awx_client` (Tasks 1-3)
- Produces (HTTP): `GET /api/v1/awx/config`, `PUT /api/v1/awx/config`, `POST /api/v1/awx/launch`, `GET /api/v1/awx/jobs/{job_id}`, `GET /api/v1/awx/schedules`, `PUT /api/v1/awx/schedules/{schedule_id}`

- [ ] **Step 1: Write the failing test**

Create `services/hmdl-api/tests/test_awx_api.py`:

```python
"""API tests for the AWX router with awx_client mocked."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


def test_config_returns_unavailable_when_not_configured():
    with patch("app.routers.awx.awx_client.is_configured", return_value=False):
        client = TestClient(app)
        resp = client.get("/api/v1/awx/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["awx_available"] is False
    assert body["extra_vars"] == {}


def test_config_returns_data_when_configured():
    with patch("app.routers.awx.awx_client.is_configured", return_value=True), \
         patch("app.routers.awx.awx_client.get_extra_vars", return_value={"dry_run": True}), \
         patch("app.routers.awx.awx_client.list_schedules", return_value=[{"id": 1, "enabled": True}]):
        client = TestClient(app)
        resp = client.get("/api/v1/awx/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["awx_available"] is True
    assert body["extra_vars"] == {"dry_run": True}
    assert body["schedules"] == [{"id": 1, "enabled": True}]


def test_put_config_rejected_when_not_configured():
    with patch("app.routers.awx.awx_client.is_configured", return_value=False):
        client = TestClient(app)
        resp = client.put("/api/v1/awx/config", json={"extra_vars": {"dry_run": True}})
    assert resp.status_code == 503


def test_put_config_patches_when_configured():
    with patch("app.routers.awx.awx_client.is_configured", return_value=True), \
         patch("app.routers.awx.awx_client.patch_extra_vars", return_value={"dry_run": True}) as mp:
        client = TestClient(app)
        resp = client.put("/api/v1/awx/config", json={"extra_vars": {"dry_run": True}})
    assert resp.status_code == 200
    assert resp.json()["extra_vars"] == {"dry_run": True}
    mp.assert_called_once_with({"dry_run": True})


def test_launch_returns_job_id():
    with patch("app.routers.awx.awx_client.is_configured", return_value=True), \
         patch("app.routers.awx.awx_client.launch", return_value=501):
        client = TestClient(app)
        resp = client.post("/api/v1/awx/launch", json={"extra_vars": {"dry_run": True}})
    assert resp.status_code == 200
    assert resp.json()["job_id"] == 501


def test_get_job_status():
    with patch("app.routers.awx.awx_client.is_configured", return_value=True), \
         patch("app.routers.awx.awx_client.get_job", return_value={"job_id": 501, "status": "running"}):
        client = TestClient(app)
        resp = client.get("/api/v1/awx/jobs/501")
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"


def test_put_schedule_toggle():
    with patch("app.routers.awx.awx_client.is_configured", return_value=True), \
         patch("app.routers.awx.awx_client.set_schedule_enabled", return_value={"id": 3, "enabled": False}):
        client = TestClient(app)
        resp = client.put("/api/v1/awx/schedules/3", json={"enabled": False})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/hmdl-api && $PY -m pytest tests/test_awx_api.py -v`
Expected: FAIL — 404 on all routes (router not registered) / import error.

- [ ] **Step 3: Create the router**

Create `services/hmdl-api/app/routers/awx.py`:

```python
"""AWX control routes: runtime config (extra_vars), launch, job status, schedules."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import awx_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/awx", tags=["awx"])


class ConfigUpdate(BaseModel):
    extra_vars: dict


class LaunchRequest(BaseModel):
    extra_vars: dict | None = None


class ScheduleUpdate(BaseModel):
    enabled: bool


@router.get("/config")
def get_config():
    if not awx_client.is_configured():
        return {"awx_available": False, "reason": "AWX not configured", "extra_vars": {}, "schedules": []}
    try:
        extra_vars = awx_client.get_extra_vars()
        schedules = awx_client.list_schedules()
    except Exception as exc:  # noqa: BLE001
        logger.warning("AWX config fetch failed: %s", exc)
        return {"awx_available": False, "reason": str(exc), "extra_vars": {}, "schedules": []}
    return {"awx_available": True, "reason": None, "extra_vars": extra_vars, "schedules": schedules}


@router.put("/config")
def put_config(body: ConfigUpdate):
    if not awx_client.is_configured():
        raise HTTPException(status_code=503, detail="AWX not configured")
    try:
        updated = awx_client.patch_extra_vars(body.extra_vars)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"AWX update failed: {exc}") from exc
    return {"awx_available": True, "extra_vars": updated}


@router.post("/launch")
def launch(body: LaunchRequest):
    if not awx_client.is_configured():
        raise HTTPException(status_code=503, detail="AWX not configured")
    try:
        job_id = awx_client.launch(body.extra_vars)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"AWX launch failed: {exc}") from exc
    return {"job_id": job_id}


@router.get("/jobs/{job_id}")
def get_job(job_id: int):
    if not awx_client.is_configured():
        raise HTTPException(status_code=503, detail="AWX not configured")
    try:
        return awx_client.get_job(job_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"AWX job fetch failed: {exc}") from exc


@router.get("/schedules")
def get_schedules():
    if not awx_client.is_configured():
        return {"awx_available": False, "items": []}
    try:
        return {"awx_available": True, "items": awx_client.list_schedules()}
    except Exception as exc:  # noqa: BLE001
        return {"awx_available": False, "items": [], "reason": str(exc)}


@router.put("/schedules/{schedule_id}")
def put_schedule(schedule_id: int, body: ScheduleUpdate):
    if not awx_client.is_configured():
        raise HTTPException(status_code=503, detail="AWX not configured")
    try:
        return awx_client.set_schedule_enabled(schedule_id, body.enabled)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"AWX schedule update failed: {exc}") from exc
```

- [ ] **Step 4: Register the router in `main.py`**

In `services/hmdl-api/app/main.py`, change the import line `from app.routers import collectors` to:

```python
from app.routers import awx, collectors
```

Then, after the existing `app.include_router(collectors.router, ...)` block, add:

```python
app.include_router(
    awx.router,
    prefix="/api/v1",
    dependencies=_auth_dep,
)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd services/hmdl-api && $PY -m pytest tests/test_awx_api.py -v`
Expected: PASS (7 tests).

- [ ] **Step 6: Run the whole hmdl-api suite (no regressions)**

Run: `cd services/hmdl-api && $PY -m pytest -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add services/hmdl-api/app/routers/awx.py services/hmdl-api/app/main.py services/hmdl-api/tests/test_awx_api.py
git commit -m "feat(hmdl-api): AWX control router (config/launch/job/schedules)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: GUI api_client AWX wrappers

**Files:**
- Modify: `src/services/api_client.py` (append after the HMDL coverage section, ~line 3166)
- Test: `tests/test_api_client_hmdl_awx.py`

**Interfaces:**
- Consumes: `_get_client_hmdl()`, `_get_json`, `_put_json`, `_post_json`, `_HTTP_ERRORS`, `logger` (all existing in `api_client.py`)
- Produces:
  - `get_hmdl_awx_config() -> dict[str, Any]`  (never raises; returns `{"awx_available": False, ...}` on error)
  - `put_hmdl_awx_config(extra_vars: dict) -> dict[str, Any]`  (raises on HTTP error — callback surfaces it)
  - `launch_hmdl_awx_job(extra_vars: dict | None = None) -> dict[str, Any]`  (raises on HTTP error)
  - `get_hmdl_awx_job(job_id: int) -> dict[str, Any]`  (never raises)
  - `set_hmdl_awx_schedule(schedule_id: int, enabled: bool) -> dict[str, Any]`  (raises on HTTP error)

- [ ] **Step 1: Write the failing test**

Create `tests/test_api_client_hmdl_awx.py`:

```python
"""Tests for HMDL AWX api_client wrappers (hmdl-api client mocked)."""

from unittest.mock import MagicMock, patch

from src.services import api_client as api


def _resp(payload):
    r = MagicMock()
    r.json.return_value = payload
    r.content = b"x"
    r.raise_for_status.return_value = None
    return r


def test_get_hmdl_awx_config_ok():
    client = MagicMock()
    client.get.return_value = _resp({"awx_available": True, "extra_vars": {"dry_run": True}, "schedules": []})
    with patch.object(api, "_get_client_hmdl", return_value=client):
        out = api.get_hmdl_awx_config()
    assert out["awx_available"] is True
    assert out["extra_vars"] == {"dry_run": True}


def test_get_hmdl_awx_config_swallows_errors():
    client = MagicMock()
    client.get.side_effect = api._HTTP_ERRORS[0]("boom") if isinstance(api._HTTP_ERRORS, tuple) else Exception("boom")
    with patch.object(api, "_get_client_hmdl", return_value=client):
        out = api.get_hmdl_awx_config()
    assert out["awx_available"] is False
    assert out["extra_vars"] == {}


def test_put_hmdl_awx_config_sends_body():
    client = MagicMock()
    client.put.return_value = _resp({"awx_available": True, "extra_vars": {"dry_run": True}})
    with patch.object(api, "_get_client_hmdl", return_value=client):
        out = api.put_hmdl_awx_config({"dry_run": True})
    assert out["extra_vars"] == {"dry_run": True}
    assert client.put.call_args.kwargs["json"] == {"extra_vars": {"dry_run": True}}


def test_launch_hmdl_awx_job():
    client = MagicMock()
    client.post.return_value = _resp({"job_id": 501})
    with patch.object(api, "_get_client_hmdl", return_value=client):
        out = api.launch_hmdl_awx_job({"dry_run": True})
    assert out["job_id"] == 501


def test_get_hmdl_awx_job_swallows_errors():
    client = MagicMock()
    client.get.side_effect = Exception("boom")
    with patch.object(api, "_get_client_hmdl", return_value=client):
        out = api.get_hmdl_awx_job(501)
    assert out["job_id"] == 501
    assert out["status"] == "unknown"


def test_set_hmdl_awx_schedule():
    client = MagicMock()
    client.put.return_value = _resp({"id": 3, "enabled": False})
    with patch.object(api, "_get_client_hmdl", return_value=client):
        out = api.set_hmdl_awx_schedule(3, False)
    assert out == {"id": 3, "enabled": False}
```

- [ ] **Step 2: Run test to verify it fails**

Run (from worktree root): `$PY -m pytest tests/test_api_client_hmdl_awx.py -v`
Expected: FAIL — `AttributeError: module 'src.services.api_client' has no attribute 'get_hmdl_awx_config'`.

- [ ] **Step 3: Add the wrappers**

In `src/services/api_client.py`, append immediately after the `get_hmdl_coverage(...)` function (end of the HMDL section, ~line 3166):

```python
def get_hmdl_awx_config() -> dict[str, Any]:
    """AWX runtime config (non-secret extra_vars) + schedules. Never raises."""
    try:
        data = _get_json(_get_client_hmdl(), "/api/v1/awx/config")
        if isinstance(data, dict):
            return data
    except _HTTP_ERRORS as exc:
        logger.warning("hmdl-api awx config unavailable: %s", exc)
    return {"awx_available": False, "extra_vars": {}, "schedules": [], "reason": "unavailable"}


def put_hmdl_awx_config(extra_vars: dict[str, Any]) -> dict[str, Any]:
    """PATCH the AWX job template extra_vars (whitelisted keys). Raises on error."""
    return _put_json(_get_client_hmdl(), "/api/v1/awx/config", {"extra_vars": extra_vars})


def launch_hmdl_awx_job(extra_vars: dict[str, Any] | None = None) -> dict[str, Any]:
    """Launch the netbox-zabbix AWX job. Raises on error."""
    body = {"extra_vars": extra_vars} if extra_vars else {}
    return _post_json(_get_client_hmdl(), "/api/v1/awx/launch", body)


def get_hmdl_awx_job(job_id: int) -> dict[str, Any]:
    """AWX job status. Never raises."""
    try:
        data = _get_json(_get_client_hmdl(), f"/api/v1/awx/jobs/{int(job_id)}")
        if isinstance(data, dict):
            return data
    except _HTTP_ERRORS as exc:
        logger.warning("hmdl-api awx job unavailable: %s", exc)
    return {"job_id": job_id, "status": "unknown"}


def set_hmdl_awx_schedule(schedule_id: int, enabled: bool) -> dict[str, Any]:
    """Enable/disable an AWX schedule. Raises on error."""
    return _put_json(_get_client_hmdl(), f"/api/v1/awx/schedules/{int(schedule_id)}", {"enabled": bool(enabled)})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$PY -m pytest tests/test_api_client_hmdl_awx.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/services/api_client.py tests/test_api_client_hmdl_awx.py
git commit -m "feat(gui): api_client wrappers for HMDL AWX config/launch/job/schedule

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: GUI page — layout, field specs, read display + unavailable banner

**Files:**
- Create: `src/pages/settings/integrations/hmdl_config.py`
- Test: `tests/test_hmdl_config_page.py`

**Interfaces:**
- Consumes: `src.services.api_client.get_hmdl_awx_config`
- Produces:
  - `FIELD_SPECS: list[dict]`  (each `{"key", "kind", "label", "section", ...}`; `kind ∈ {"select","switch","number","text","tags"}`)
  - `build_layout(search: str | None = None) -> html.Div`
  - Helper `_find_by_id(layout, comp_id)` is NOT part of the module — tests walk the tree themselves.

- [ ] **Step 1: Write the failing test**

Create `tests/test_hmdl_config_page.py`:

```python
"""Smoke + behavior tests for the HMDL configuration page."""

from unittest.mock import patch

import dash_mantine_components as dmc
from dash import html

from src.pages.settings.integrations import hmdl_config as page


def _walk(node):
    yield node
    children = getattr(node, "children", None)
    if children is None:
        return
    if not isinstance(children, (list, tuple)):
        children = [children]
    for c in children:
        yield from _walk(c)


def _ids(layout):
    out = []
    for n in _walk(layout):
        cid = getattr(n, "id", None)
        if cid is not None:
            out.append(cid)
    return out


def test_layout_renders_banner_when_awx_unavailable():
    with patch.object(page.api, "get_hmdl_awx_config",
                      return_value={"awx_available": False, "extra_vars": {}, "schedules": []}):
        layout = page.build_layout()
    assert isinstance(layout, html.Div)
    # a visible Alert somewhere in the tree
    assert any(isinstance(n, dmc.Alert) for n in _walk(layout))


def test_layout_prefills_fields_from_extra_vars():
    with patch.object(page.api, "get_hmdl_awx_config",
                      return_value={"awx_available": True,
                                    "extra_vars": {"dry_run": True, "device_limit": 7, "device_source": "loki"},
                                    "schedules": []}):
        layout = page.build_layout()
    ids = _ids(layout)
    # value fields and bool fields are addressed by pattern-matching ids
    assert {"type": "hmdlcfg-val", "key": "device_source"} in ids
    assert {"type": "hmdlcfg-bool", "key": "dry_run"} in ids
    assert {"type": "hmdlcfg-val", "key": "device_limit"} in ids


def test_field_specs_cover_whitelist():
    from app.services import awx_client  # noqa: F401  (only to document intent)
    # every spec key is a string; there are no duplicate keys
    keys = [f["key"] for f in page.FIELD_SPECS]
    assert len(keys) == len(set(keys))
    assert "dry_run" in keys and "device_source" in keys and "mail_recipients" in keys
```

Note: the `from app.services import awx_client` line will fail under the GUI test path (hmdl-api is not on `sys.path`). Replace that line's intent by simply asserting on `page.FIELD_SPECS` — remove the import. Final `test_field_specs_cover_whitelist` body:

```python
def test_field_specs_cover_whitelist():
    keys = [f["key"] for f in page.FIELD_SPECS]
    assert len(keys) == len(set(keys))
    assert "dry_run" in keys and "device_source" in keys and "mail_recipients" in keys
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PY -m pytest tests/test_hmdl_config_page.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.pages.settings.integrations.hmdl_config'`.

- [ ] **Step 3: Create the page (layout only; callbacks in Task 7)**

Create `src/pages/settings/integrations/hmdl_config.py`:

```python
"""Integrations — HMDL netbox-zabbix AWX run & schedule configuration (Tier A).

Reads/writes only non-secret runtime variables of the AWX job template.
Secrets (DB/Zabbix/NetBox passwords, tokens, SNMP passphrases) stay in AWX
Credentials / Vault and are never shown or edited here.
"""

from __future__ import annotations

import dash
from dash import Input, Output, State, callback, ctx, dcc, html
import dash_mantine_components as dmc

from src.services import api_client as api

_PATH = "/administration/integrations/hmdl/config"

_SOURCE_OPTS = [{"value": "loki", "label": "loki (NetBox)"}, {"value": "datalake", "label": "datalake (Postgres)"}]

# section, key, kind, label. kind ∈ {"select","switch","number","text","tags"}
FIELD_SPECS: list[dict] = [
    # Source routing
    {"section": "Kaynak yönlendirme", "key": "device_source", "kind": "select", "label": "device_source", "opts": _SOURCE_OPTS},
    {"section": "Kaynak yönlendirme", "key": "platform_source", "kind": "select", "label": "platform_source", "opts": _SOURCE_OPTS},
    {"section": "Kaynak yönlendirme", "key": "virtual_fw_source", "kind": "select", "label": "virtual_fw_source", "opts": _SOURCE_OPTS},
    # Sync scope
    {"section": "Sync kapsamı", "key": "sync_devices", "kind": "switch", "label": "sync_devices"},
    {"section": "Sync kapsamı", "key": "sync_platforms", "kind": "switch", "label": "sync_platforms"},
    {"section": "Sync kapsamı", "key": "sync_virtual_fws", "kind": "switch", "label": "sync_virtual_fws"},
    {"section": "Sync kapsamı", "key": "report_izlenmeyecek", "kind": "switch", "label": "report_izlenmeyecek"},
    {"section": "Sync kapsamı", "key": "create_devices_disabled", "kind": "switch", "label": "create_devices_disabled"},
    {"section": "Sync kapsamı", "key": "create_platforms_disabled", "kind": "switch", "label": "create_platforms_disabled"},
    {"section": "Sync kapsamı", "key": "create_virtual_fws_disabled", "kind": "switch", "label": "create_virtual_fws_disabled"},
    # Execution
    {"section": "Çalıştırma", "key": "dry_run", "kind": "switch", "label": "dry_run"},
    {"section": "Çalıştırma", "key": "only_fetch", "kind": "switch", "label": "only_fetch"},
    {"section": "Çalıştırma", "key": "debug_mode", "kind": "switch", "label": "debug_mode"},
    {"section": "Çalıştırma", "key": "parallel_compare_ignore_errors", "kind": "switch", "label": "parallel_compare_ignore_errors"},
    {"section": "Çalıştırma", "key": "device_limit", "kind": "number", "label": "device_limit (0=limitsiz)"},
    {"section": "Çalıştırma", "key": "parallel_compare_workers", "kind": "number", "label": "parallel_compare_workers"},
    {"section": "Çalıştırma", "key": "location_filter", "kind": "text", "label": "location_filter"},
    # Logging + email
    {"section": "Log & e-posta", "key": "hmdl_log_enabled", "kind": "switch", "label": "hmdl_log_enabled"},
    {"section": "Log & e-posta", "key": "mail_recipients", "kind": "tags", "label": "mail_recipients"},
    {"section": "Log & e-posta", "key": "mail_from", "kind": "text", "label": "mail_from"},
    # Endpoints (no passwords)
    {"section": "Bağlantı adresleri (parolasız)", "key": "zabbix_url", "kind": "text", "label": "zabbix_url"},
    {"section": "Bağlantı adresleri (parolasız)", "key": "netbox_url", "kind": "text", "label": "netbox_url"},
    {"section": "Bağlantı adresleri (parolasız)", "key": "discovery_db_host", "kind": "text", "label": "discovery_db_host"},
    {"section": "Bağlantı adresleri (parolasız)", "key": "discovery_db_port", "kind": "text", "label": "discovery_db_port"},
    {"section": "Bağlantı adresleri (parolasız)", "key": "discovery_db_name", "kind": "text", "label": "discovery_db_name"},
]


def _build_field(spec: dict, current: dict):
    key = spec["key"]
    kind = spec["kind"]
    label = spec["label"]
    val = current.get(key)
    if kind == "switch":
        return dmc.Switch(
            id={"type": "hmdlcfg-bool", "key": key},
            label=label,
            checked=bool(val),
            size="sm",
        )
    if kind == "select":
        return dmc.Select(
            id={"type": "hmdlcfg-val", "key": key},
            label=label,
            data=spec["opts"],
            value=str(val) if val is not None else None,
            size="xs",
        )
    if kind == "number":
        return dmc.NumberInput(
            id={"type": "hmdlcfg-val", "key": key},
            label=label,
            value=int(val) if isinstance(val, (int, float)) else 0,
            min=0,
            size="xs",
        )
    if kind == "tags":
        vals = val if isinstance(val, list) else ([val] if val else [])
        return dmc.TagsInput(
            id={"type": "hmdlcfg-val", "key": key},
            label=label,
            value=[str(v) for v in vals],
            size="xs",
        )
    # text
    return dmc.TextInput(
        id={"type": "hmdlcfg-val", "key": key},
        label=label,
        value="" if val is None else str(val),
        size="xs",
    )


def _sections(current: dict):
    order: list[str] = []
    grouped: dict[str, list] = {}
    for spec in FIELD_SPECS:
        sec = spec["section"]
        if sec not in grouped:
            grouped[sec] = []
            order.append(sec)
        grouped[sec].append(_build_field(spec, current))
    papers = []
    for sec in order:
        papers.append(
            dmc.Paper(
                p="md", radius="md", withBorder=True, mb="md",
                children=[
                    dmc.Title(sec, order=5, mb="sm"),
                    dmc.SimpleGrid(cols={"base": 1, "md": 3}, spacing="sm", children=grouped[sec]),
                ],
            )
        )
    return papers


def _schedule_rows(schedules: list[dict]):
    rows = []
    for s in schedules or []:
        sid = s.get("id")
        rows.append(
            dmc.Group(
                justify="space-between",
                children=[
                    dmc.Text(f"{s.get('name') or sid} — next: {s.get('next_run') or '-'}", size="sm"),
                    dmc.Switch(
                        id={"type": "hmdlcfg-sched", "sid": sid},
                        checked=bool(s.get("enabled")),
                        label="enabled",
                        size="sm",
                    ),
                ],
            )
        )
    return rows or [dmc.Text("Schedule yok.", size="sm", c="dimmed")]


def build_layout(search: str | None = None) -> html.Div:
    cfg = api.get_hmdl_awx_config()
    available = bool(cfg.get("awx_available"))
    current = cfg.get("extra_vars") or {}
    schedules = cfg.get("schedules") or []

    banner = None
    if not available:
        banner = dmc.Alert(
            color="yellow",
            title="AWX yapılandırılmadı",
            children="hmdl-api'de AWX_API_URL / AWX_TOKEN / AWX_NETBOX_ZABBIX_JT_ID ayarlanınca "
                     "değişkenler ve schedule buradan yönetilebilecek. Ekran salt görünümde.",
            mb="md",
        )

    run_bar = dmc.Paper(
        p="md", radius="md", withBorder=True, mb="md",
        children=[
            dmc.Group(
                children=[
                    dmc.Button("Kaydet", id="hmdlcfg-save", size="sm", disabled=not available),
                    dmc.Button("Şimdi çalıştır", id="hmdlcfg-run", size="sm", color="teal", variant="light", disabled=not available),
                    dmc.Switch(id="hmdlcfg-run-dryrun", label="dry_run override", size="sm"),
                ],
            ),
            html.Div(id="hmdlcfg-save-msg", style={"marginTop": "8px"}),
            html.Div(id="hmdlcfg-run-msg", style={"marginTop": "8px"}),
        ],
    )

    return html.Div(
        [
            dmc.Stack(
                gap="xs", mb="md",
                children=[
                    dmc.Title("HMDL netbox-zabbix — Çalıştırma yapılandırması", order=3),
                    dmc.Text(
                        "AWX job template'inin gizli-olmayan çalışma değişkenleri (extra_vars). "
                        "Parolalar/token'lar AWX Credentials/Vault'ta kalır; burada görünmez.",
                        size="sm", c="dimmed",
                    ),
                ],
            ),
            banner if banner else html.Div(),
            run_bar,
            *_sections(current),
            dmc.Paper(
                p="md", radius="md", withBorder=True, mb="md",
                children=[dmc.Title("Schedule", order=5, mb="sm"),
                          html.Div(id="hmdlcfg-sched-msg", style={"marginBottom": "8px"}),
                          dmc.Stack(gap="xs", children=_schedule_rows(schedules))],
            ),
            # job-status polling plumbing (callbacks in Task 7)
            dcc.Store(id="hmdlcfg-job-store"),
            dcc.Interval(id="hmdlcfg-job-poll", interval=4000, disabled=True),
        ]
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$PY -m pytest tests/test_hmdl_config_page.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/pages/settings/integrations/hmdl_config.py tests/test_hmdl_config_page.py
git commit -m "feat(gui): HMDL config page layout (AWX extra_vars form + schedule view)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: GUI page — Save / Run-now / poll / schedule-toggle callbacks

**Files:**
- Modify: `src/pages/settings/integrations/hmdl_config.py` (append callbacks)
- Test: `tests/test_hmdl_config_callbacks.py`

**Interfaces:**
- Consumes: `api.put_hmdl_awx_config`, `api.launch_hmdl_awx_job`, `api.get_hmdl_awx_job`, `api.set_hmdl_awx_schedule`
- Produces (importable helper for testability — keeps callbacks thin):
  - `assemble_extra_vars(val_ids, val_values, bool_ids, bool_values) -> dict`
  - Callbacks: `_save_cb`, `_run_cb`, `_poll_cb`, `_sched_cb` (registered via `@callback`)

- [ ] **Step 1: Write the failing test**

Create `tests/test_hmdl_config_callbacks.py`:

```python
"""Behavior tests for HMDL config page helper + save callback."""

from unittest.mock import patch

import dash_mantine_components as dmc

from src.pages.settings.integrations import hmdl_config as page


def test_assemble_extra_vars_merges_val_and_bool():
    val_ids = [{"type": "hmdlcfg-val", "key": "device_source"}, {"type": "hmdlcfg-val", "key": "device_limit"}]
    val_values = ["loki", 7]
    bool_ids = [{"type": "hmdlcfg-bool", "key": "dry_run"}]
    bool_values = [True]
    out = page.assemble_extra_vars(val_ids, val_values, bool_ids, bool_values)
    assert out == {"device_source": "loki", "device_limit": 7, "dry_run": True}


def test_assemble_extra_vars_skips_empty_text():
    val_ids = [{"type": "hmdlcfg-val", "key": "location_filter"}, {"type": "hmdlcfg-val", "key": "mail_from"}]
    val_values = ["", "a@b.c"]
    out = page.assemble_extra_vars(val_ids, val_values, [], [])
    assert out == {"mail_from": "a@b.c"}  # empty string dropped


def test_save_cb_success():
    with patch.object(page.api, "put_hmdl_awx_config", return_value={"awx_available": True, "extra_vars": {}}):
        msg = page._save_cb(
            1,
            [{"type": "hmdlcfg-val", "key": "device_source"}], ["loki"],
            [{"type": "hmdlcfg-bool", "key": "dry_run"}], [True],
        )
    assert isinstance(msg, dmc.Alert)
    assert msg.color == "green"


def test_save_cb_error_surfaces_alert():
    with patch.object(page.api, "put_hmdl_awx_config", side_effect=Exception("nope")):
        msg = page._save_cb(
            1,
            [{"type": "hmdlcfg-val", "key": "device_source"}], ["loki"],
            [], [],
        )
    assert isinstance(msg, dmc.Alert)
    assert msg.color == "red"


def test_run_cb_starts_poll_and_stores_job():
    with patch.object(page.api, "launch_hmdl_awx_job", return_value={"job_id": 501}):
        store, poll_disabled, msg = page._run_cb(1, True)
    assert store == {"job_id": 501}
    assert poll_disabled is False
    assert isinstance(msg, dmc.Alert)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PY -m pytest tests/test_hmdl_config_callbacks.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'assemble_extra_vars'`.

- [ ] **Step 3: Append helper + callbacks to `hmdl_config.py`**

Append to `src/pages/settings/integrations/hmdl_config.py`:

```python
_NUMERIC_KEYS = {"device_limit", "parallel_compare_workers"}


def assemble_extra_vars(val_ids, val_values, bool_ids, bool_values) -> dict:
    out: dict = {}
    for cid, value in zip(val_ids or [], val_values or []):
        key = cid.get("key")
        if not key:
            continue
        if isinstance(value, str):
            if value == "":
                continue
            out[key] = value
        elif value is None:
            continue
        elif key in _NUMERIC_KEYS:
            out[key] = int(value)
        else:
            out[key] = value
    for cid, value in zip(bool_ids or [], bool_values or []):
        key = cid.get("key")
        if key:
            out[key] = bool(value)
    return out


@callback(
    Output("hmdlcfg-save-msg", "children"),
    Input("hmdlcfg-save", "n_clicks"),
    State({"type": "hmdlcfg-val", "key": dash.ALL}, "value"),
    State({"type": "hmdlcfg-val", "key": dash.ALL}, "id"),
    State({"type": "hmdlcfg-bool", "key": dash.ALL}, "checked"),
    State({"type": "hmdlcfg-bool", "key": dash.ALL}, "id"),
    prevent_initial_call=True,
)
def _save_cb(_n, val_values, val_ids, bool_values, bool_ids):
    extra_vars = assemble_extra_vars(val_ids, val_values, bool_ids, bool_values)
    try:
        api.put_hmdl_awx_config(extra_vars)
        return dmc.Alert(color="green", title="Kaydedildi — bir sonraki (scheduled/manual) çalıştırma bunu kullanır.")
    except Exception as exc:  # noqa: BLE001
        return dmc.Alert(color="red", title="Kaydetme başarısız", children=str(exc))


@callback(
    Output("hmdlcfg-job-store", "data"),
    Output("hmdlcfg-job-poll", "disabled"),
    Output("hmdlcfg-run-msg", "children"),
    Input("hmdlcfg-run", "n_clicks"),
    State("hmdlcfg-run-dryrun", "checked"),
    prevent_initial_call=True,
)
def _run_cb(_n, dryrun):
    try:
        res = api.launch_hmdl_awx_job({"dry_run": True} if dryrun else None)
        job_id = res.get("job_id")
        return {"job_id": job_id}, False, dmc.Alert(color="blue", title=f"Çalıştırıldı — job #{job_id}")
    except Exception as exc:  # noqa: BLE001
        return dash.no_update, True, dmc.Alert(color="red", title="Çalıştırma başarısız", children=str(exc))


@callback(
    Output("hmdlcfg-run-msg", "children", allow_duplicate=True),
    Output("hmdlcfg-job-poll", "disabled", allow_duplicate=True),
    Input("hmdlcfg-job-poll", "n_intervals"),
    State("hmdlcfg-job-store", "data"),
    prevent_initial_call=True,
)
def _poll_cb(_n, store):
    job_id = (store or {}).get("job_id")
    if not job_id:
        return dash.no_update, True
    job = api.get_hmdl_awx_job(int(job_id))
    status = job.get("status") or "unknown"
    done = status in ("successful", "failed", "error", "canceled")
    color = "green" if status == "successful" else ("red" if status in ("failed", "error") else "blue")
    return dmc.Alert(color=color, title=f"job #{job_id}: {status}"), bool(done)


@callback(
    Output("hmdlcfg-sched-msg", "children"),
    Input({"type": "hmdlcfg-sched", "sid": dash.ALL}, "checked"),
    State({"type": "hmdlcfg-sched", "sid": dash.ALL}, "id"),
    prevent_initial_call=True,
)
def _sched_cb(checked_values, ids):
    trig = ctx.triggered_id
    if not isinstance(trig, dict) or trig.get("type") != "hmdlcfg-sched":
        return dash.no_update
    sid = trig.get("sid")
    # find the new value for the triggered switch
    new_val = None
    for cid, val in zip(ids or [], checked_values or []):
        if cid.get("sid") == sid:
            new_val = bool(val)
            break
    try:
        api.set_hmdl_awx_schedule(int(sid), bool(new_val))
        return dmc.Alert(color="green", title=f"Schedule #{sid} güncellendi ({'enabled' if new_val else 'disabled'}).")
    except Exception as exc:  # noqa: BLE001
        return dmc.Alert(color="red", title="Schedule güncelleme başarısız", children=str(exc))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$PY -m pytest tests/test_hmdl_config_callbacks.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/pages/settings/integrations/hmdl_config.py tests/test_hmdl_config_callbacks.py
git commit -m "feat(gui): HMDL config page callbacks (save/run/poll/schedule)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Wiring — settings shell tab, page builder, permission catalog + resolver

**Files:**
- Modify: `src/pages/settings/shell.py` (import; `HMDL_TABS`; `_PAGE_BUILDERS`)
- Modify: `src/auth/permission_catalog.py` (new `page:settings_hmdl_config` node)
- Modify: `src/auth/permission_service.py` (resolver branch)
- Modify: `app.py` (register the page module's callbacks — import for side effects)
- Test: `tests/test_hmdl_config_wiring.py`

**Interfaces:**
- Consumes: `hmdl_config.build_layout` (Task 6)
- Produces: route `/administration/integrations/hmdl/config` → `("page:settings_hmdl_config", hmdl_config_page.build_layout)`; permission code `page:settings_hmdl_config`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_hmdl_config_wiring.py`:

```python
"""Wiring tests: shell registration, resolver, permission catalog node."""

from src.pages.settings import shell
from src.auth.permission_service import resolve_pathname_to_page_code


def test_shell_registers_hmdl_config_route():
    assert "/administration/integrations/hmdl/config" in shell._PAGE_BUILDERS
    code, builder = shell._PAGE_BUILDERS["/administration/integrations/hmdl/config"]
    assert code == "page:settings_hmdl_config"
    assert callable(builder)


def test_hmdl_tabs_include_configuration():
    hrefs = [h for h, _l, _c in shell.HMDL_TABS]
    assert "/administration/integrations/hmdl/config" in hrefs


def test_resolver_maps_config_path():
    assert resolve_pathname_to_page_code(
        "/administration/integrations/hmdl/config"
    ) == "page:settings_hmdl_config"


def test_resolver_still_maps_hmdl_overview():
    assert resolve_pathname_to_page_code(
        "/administration/integrations/hmdl"
    ) == "page:settings_hmdl_overview"


def test_permission_catalog_has_config_node():
    from src.auth.permission_catalog import build_default_permission_roots

    roots = build_default_permission_roots()

    def _codes(nodes):
        for n in nodes:
            yield n.get("code")
            yield from _codes(n.get("children", []) or [])

    all_codes = set(_codes(roots))
    assert "page:settings_hmdl_config" in all_codes
```

Note: if `build_default_permission_roots` returns objects rather than dicts, adapt `_codes` to read attributes (`n.code`, `n.children`). Verify the node shape when implementing (the `_n(...)` helper defines it).

- [ ] **Step 2: Run test to verify it fails**

Run: `$PY -m pytest tests/test_hmdl_config_wiring.py -v`
Expected: FAIL — route/tab/code/catalog assertions fail.

- [ ] **Step 3: Register in `shell.py`**

In `src/pages/settings/shell.py`:

(a) After the line `from src.pages.settings.integrations import hmdl_coverage as hmdl_coverage_page`, add:

```python
from src.pages.settings.integrations import hmdl_config as hmdl_config_page
```

(b) In `HMDL_TABS`, add a 4th tuple:

```python
    (f"{_A}/integrations/hmdl/config", "Configuration", "page:settings_hmdl_config"),
```

(c) In `_PAGE_BUILDERS`, after the `/integrations/hmdl/coverage` entry, add:

```python
    f"{_A}/integrations/hmdl/config": ("page:settings_hmdl_config", hmdl_config_page.build_layout),
```

- [ ] **Step 4: Add permission node in `permission_catalog.py`**

In `src/auth/permission_catalog.py`, immediately after the `page:settings_hmdl_coverage` `_n(...)` node (ends ~line 362), add:

```python
            _n(
                "page:settings_hmdl_config",
                "HMDL netbox-zabbix run configuration",
                "config",
                route_pattern="/administration/integrations/hmdl/config",
                sort_order=59,
            ),
```

- [ ] **Step 5: Add resolver branch in `permission_service.py`**

In `src/auth/permission_service.py`, inside `resolve_pathname_to_page_code`, add BEFORE the `if admin_p.rstrip("/") == "/administration/integrations/hmdl":` line (i.e. next to the coverage/sync-health branches, ~line 139):

```python
        if admin_p.startswith("/administration/integrations/hmdl/config"):
            return "page:settings_hmdl_config"
```

- [ ] **Step 6: Register page callbacks in `app.py`**

The page uses the module-level `@callback` decorator, so its callbacks register when the module is imported. `shell.py` imports it (Step 3a) and `app.py` imports `shell`, so it is already reachable. No extra `app.py` edit is required. Verify by grep:

Run: `grep -n "hmdl_config" src/pages/settings/shell.py`
Expected: the import line and the `_PAGE_BUILDERS` entry are present.

- [ ] **Step 7: Run tests to verify they pass**

Run: `$PY -m pytest tests/test_hmdl_config_wiring.py -v`
Expected: PASS (5 tests).

- [ ] **Step 8: Commit**

```bash
git add src/pages/settings/shell.py src/auth/permission_catalog.py src/auth/permission_service.py tests/test_hmdl_config_wiring.py
git commit -m "feat(gui): wire HMDL Configuration sub-page (shell tab, route, permission)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Deploy env wiring + docs + full regression

**Files:**
- Modify: `docker-compose.yml` (add AWX env to the `hmdl-api` service)
- Modify: `.env.example` (document AWX vars)
- Modify: `docs/PROJECT_STANDARDS.md` OR create `docs/HMDL_CONFIG.md` (short operator note)

**Interfaces:** none (deploy/docs only).

- [ ] **Step 1: Add AWX env to `hmdl-api` in `docker-compose.yml`**

Find the `hmdl-api` service `environment:` block (near line 370-385, alongside `HMDL_DB_*`) and add:

```yaml
      AWX_ENABLED: ${AWX_ENABLED:-false}
      AWX_API_URL: ${AWX_API_URL:-}
      AWX_TOKEN: ${AWX_TOKEN:-}
      AWX_NETBOX_ZABBIX_JT_ID: ${AWX_NETBOX_ZABBIX_JT_ID:-}
      AWX_VERIFY_SSL: ${AWX_VERIFY_SSL:-false}
```

- [ ] **Step 2: Document in `.env.example`**

Append to `.env.example`:

```dotenv
# --- HMDL AWX integration (netbox-zabbix job template control) ---
# Generate AWX_TOKEN from the AWX web UI: User -> Tokens (scope: write).
# AWX_API_URL is the REST root, e.g. https://awx.example/api/v2
AWX_ENABLED=false
AWX_API_URL=
AWX_TOKEN=
AWX_NETBOX_ZABBIX_JT_ID=
AWX_VERIFY_SSL=false
```

- [ ] **Step 3: Write the operator note**

Create `docs/HMDL_CONFIG.md`:

```markdown
# HMDL Configuration Screen (Administration › Integrations › HMDL › Configuration)

Edits the **non-secret** runtime variables (`extra_vars`) of the netbox-zabbix
AWX job template, triggers runs, and toggles schedules. Secrets (DB/Zabbix/NetBox
passwords, tokens, SNMP passphrases) are NOT shown or edited here — they live in
AWX Credentials / Vault.

## Enabling

Set on the `hmdl-api` service (see `.env.example`):

- `AWX_ENABLED=true`
- `AWX_API_URL` — AWX REST root, e.g. `https://awx.example/api/v2`
- `AWX_TOKEN` — AWX personal access token (User → Tokens in the AWX UI)
- `AWX_NETBOX_ZABBIX_JT_ID` — the job template id (or name) for the netbox-zabbix sync
- `AWX_VERIFY_SSL` — `true` in production with valid certs

Until enabled, the screen renders in view-only mode with an "AWX yapılandırılmadı" banner.

## Behavior

- **Kaydet** → PATCHes the job template `extra_vars` (whitelisted keys only). Every
  subsequent scheduled/manual run uses the saved values.
- **Şimdi çalıştır** → launches the job template (optional `dry_run` override), then
  polls job status.
- **Schedule** switches enable/disable AWX schedules on the job template.
```

- [ ] **Step 4: Full regression across both suites**

Run:
```bash
cd services/hmdl-api && $PY -m pytest -q
```
Expected: all hmdl-api tests pass.

Run (from worktree root):
```bash
$PY -m pytest tests/test_api_client_hmdl_awx.py tests/test_hmdl_config_page.py tests/test_hmdl_config_callbacks.py tests/test_hmdl_config_wiring.py tests/test_hmdl_overview_page.py tests/test_permission_service.py -q
```
Expected: all pass (new tests + adjacent HMDL/permission tests unaffected).

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml .env.example docs/HMDL_CONFIG.md
git commit -m "chore(hmdl): AWX env wiring + operator docs for HMDL config screen

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- Route `/administration/integrations/hmdl/config` + "Configuration" tab → Task 8 ✅
- Non-secret Tier-A field set (all whitelisted keys) → Task 1 (whitelist) + Task 6 (`FIELD_SPECS`) ✅
- Show current extra_vars + schedules + banner → Task 6 ✅
- Edit + Save (PATCH extra_vars) → Task 3 (`patch_extra_vars`) + Task 4 (`PUT /awx/config`) + Task 5 + Task 7 ✅
- Run now + status poll → Task 3 (`launch`) + Task 4 + Task 5 + Task 7 ✅
- Schedule enable/disable → Task 3 + Task 4 + Task 5 + Task 7 ✅
- Secrets never read/written → Task 1 (`filter_allowed`/`is_secret_key`) enforced in read & write; tested in Tasks 1-3 ✅
- AWX client in hmdl-api, token server-side → Tasks 1-4 ✅
- Env/config (`AWX_*`) → Task 1 (config.py) + Task 9 (compose/.env) ✅
- Permission `page:settings_hmdl_config` (catalog + resolver + shell gate) → Task 8 ✅
- Error handling → structured `awx_available:false` (Task 4), `dmc.Alert` in callbacks (Task 7) ✅
- Tests with mocks; run on Python 3.11 `.venv` → every task ✅
- Phase 2 (mapping editor) explicitly out of scope → not in this plan ✅

**Placeholder scan:** No "TBD"/"handle edge cases"/"similar to". Two implementation-time verifications are flagged explicitly (permission-catalog node shape in Task 8; `_HTTP_ERRORS` tuple shape in Task 5 test) with concrete fallback instructions — not placeholders.

**Type consistency:** `filter_allowed` / `is_secret_key` / `is_configured` (Task 1) reused verbatim in Tasks 2-3. `get_extra_vars`/`patch_extra_vars`/`launch`/`get_job`/`list_schedules`/`set_schedule_enabled` names match between awx_client (Tasks 2-3), router (Task 4), api_client wrappers (Task 5), and page callbacks (Task 7). Pattern-matching ids (`hmdlcfg-val`/`hmdlcfg-bool`/`hmdlcfg-sched`) match between layout (Task 6) and callbacks (Task 7). Route string and permission code identical across Tasks 6/8.
