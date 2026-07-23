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
