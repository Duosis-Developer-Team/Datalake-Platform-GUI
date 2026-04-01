"""
HTTP client for AuraNotify SLA / downtime APIs.
Configure via AURANOTIFY_BASE_URL and AURANOTIFY_API_KEY environment variables.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

AURANOTIFY_BASE = os.getenv("AURANOTIFY_BASE_URL", "http://10.34.8.154:5001").rstrip("/")
AURANOTIFY_KEY = os.getenv("AURANOTIFY_API_KEY", "").strip()

_transport = httpx.HTTPTransport(retries=2)


def _client() -> httpx.Client:
    return httpx.Client(base_url=AURANOTIFY_BASE, timeout=20.0, transport=_transport)


def _headers() -> dict[str, str]:
    if not AURANOTIFY_KEY:
        return {}
    return {"X-API-Key": AURANOTIFY_KEY}


def get_dc_services_availability(start_date: str) -> list[dict[str, Any]]:
    """GET /api/sla/datacenter-services — all DC groups with category SLA breakdown."""
    if not AURANOTIFY_KEY:
        logger.debug("AURANOTIFY_API_KEY not set; skipping datacenter-services")
        return []
    try:
        with _client() as c:
            r = c.get(
                "/api/sla/datacenter-services",
                params={"start_date": start_date},
                headers=_headers(),
            )
            r.raise_for_status()
            data = r.json()
            return data.get("items") or []
    except Exception as exc:
        logger.warning("get_dc_services_availability failed: %s", exc)
        return []


def match_dc_group_item(items: list[dict[str, Any]], hint: str) -> Optional[dict[str, Any]]:
    """Pick the item whose group_name best matches DC name or code (substring match)."""
    hint = (hint or "").strip().lower()
    if not hint or not items:
        return None
    for it in items:
        gn = str(it.get("group_name") or "").strip().lower()
        if gn == hint:
            return it
    for it in items:
        gn = str(it.get("group_name") or "").strip().lower()
        if hint in gn or gn in hint:
            return it
    return None


def get_customer_list_aura() -> list[dict[str, Any]]:
    """GET /api/customers/list — [{id, name}, ...]."""
    if not AURANOTIFY_KEY:
        return []
    try:
        with _client() as c:
            r = c.get("/api/customers/list", headers=_headers())
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, list) else []
    except Exception as exc:
        logger.warning("get_customer_list_aura failed: %s", exc)
        return []


def get_customer_downtimes(customer_id: int, start_date: str, source: str) -> dict[str, Any]:
    """GET /api/customers/{id}/downtimes?start_date=&source=service|vm"""
    if not AURANOTIFY_KEY:
        return {}
    try:
        with _client() as c:
            r = c.get(
                f"/api/customers/{customer_id}/downtimes",
                params={"start_date": start_date, "source": source},
                headers=_headers(),
            )
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("get_customer_downtimes failed (%s): %s", source, exc)
        return {}


def resolve_customer_id(customer_name: str) -> Optional[int]:
    name = (customer_name or "").strip().lower()
    if not name:
        return None
    for row in get_customer_list_aura():
        if str(row.get("name", "")).strip().lower() == name:
            cid = row.get("id")
            try:
                return int(cid)
            except (TypeError, ValueError):
                return None
    return None


def _collect_vm_names_from_event(event: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for key in ("vm_name", "vm", "virtual_machine", "workload_name", "hostname"):
        v = event.get(key)
        if v and isinstance(v, str) and v.strip():
            names.append(v.strip())
    nested = event.get("affected_vms") or event.get("vms") or []
    if isinstance(nested, list):
        for x in nested:
            if isinstance(x, str) and x.strip():
                names.append(x.strip())
            elif isinstance(x, dict):
                for key in ("name", "vm_name", "vm"):
                    v = x.get(key)
                    if v and isinstance(v, str) and v.strip():
                        names.append(v.strip())
                        break
    return names


def vm_outage_counts_from_events(events: list[dict[str, Any]]) -> dict[str, int]:
    """Lowercased VM name -> number of downtime records affecting it."""
    counts: dict[str, int] = {}
    for e in events or []:
        if not isinstance(e, dict):
            continue
        vm_names = _collect_vm_names_from_event(e)
        if not vm_names:
            # One outage row without explicit VM: count as generic (skip per-VM badge)
            continue
        for vm in vm_names:
            k = vm.lower()
            counts[k] = counts.get(k, 0) + 1
    return counts


def get_customer_availability_bundle(customer_name: str, start_date: str) -> dict[str, Any]:
    """
    Service + VM downtimes and vm_outage_counts for virtualization VM name matching.
    """
    empty: dict[str, Any] = {
        "service_downtimes": [],
        "vm_downtimes": [],
        "vm_outage_counts": {},
        "customer_id": None,
    }
    cid = resolve_customer_id(customer_name)
    if cid is None:
        return empty
    svc_body = get_customer_downtimes(cid, start_date, "service")
    vm_body = get_customer_downtimes(cid, start_date, "vm")
    svc_events = svc_body.get("datacenter_downtimes") or []
    vm_events = vm_body.get("datacenter_downtimes") or []
    if not isinstance(svc_events, list):
        svc_events = []
    if not isinstance(vm_events, list):
        vm_events = []
    return {
        "service_downtimes": svc_events,
        "vm_downtimes": vm_events,
        "vm_outage_counts": vm_outage_counts_from_events(vm_events),
        "customer_id": cid,
    }
