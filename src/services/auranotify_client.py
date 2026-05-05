"""
HTTP client for AuraNotify SLA / downtime APIs.
Configure via AURANOTIFY_BASE_URL and AURANOTIFY_API_KEY environment variables.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

AURANOTIFY_BASE = os.getenv("AURANOTIFY_BASE_URL", "http://10.34.8.154:5001").rstrip("/")
AURANOTIFY_KEY = (
    os.getenv("AURANOTIFY_API_KEY", "").strip()
    or os.getenv("ANOTIFY_API_KEY", "").strip()
)

_transport = httpx.HTTPTransport(retries=2)


def _client() -> httpx.Client:
    return httpx.Client(base_url=AURANOTIFY_BASE, timeout=20.0, transport=_transport)


def _headers() -> dict[str, str]:
    if not AURANOTIFY_KEY:
        return {}
    return {"X-API-Key": AURANOTIFY_KEY}


def get_dc_services_availability(
    start_date: str, end_date: str | None = None
) -> list[dict[str, Any]]:
    """GET /api/sla/datacenter-services — all DC groups with category SLA breakdown.

    If the upstream service supports it, pass ``end_date`` to bound the reporting period
    (e.g. end of selected calendar year or today for the current year).
    """
    if not AURANOTIFY_KEY:
        logger.debug("AURANOTIFY_API_KEY / ANOTIFY_API_KEY not set; skipping datacenter-services")
        return []
    try:
        params: dict[str, str] = {"start_date": start_date}
        if end_date:
            params["end_date"] = end_date
        with _client() as c:
            r = c.get(
                "/api/sla/datacenter-services",
                params=params,
                headers=_headers(),
            )
            r.raise_for_status()
            data = r.json()
            if isinstance(data, list):
                return data
            items = data.get("items") or data.get("data") or data.get("results")
            return items if isinstance(items, list) else []
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
    # Match DC/site code token (e.g. DC13 in "Equinix IL2 - DC13")
    for tok in re.findall(r"\b(dc\d+|ict\d+|az\d+|uz\d+)\b", hint, flags=re.I):
        t = tok.lower()
        pat = re.compile(r"\b" + re.escape(t) + r"\b", flags=re.I)
        for it in items:
            gn = str(it.get("group_name") or "")
            if pat.search(gn):
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


def resolve_customer_ids(customer_name: str) -> list[int]:
    """
    All AuraNotify customer IDs for this GUI customer: exact name match plus names
    like ``Boyner_Dr`` when the selected customer is ``Boyner``.
    """
    prefix = (customer_name or "").strip().lower()
    if not prefix:
        return []
    ids: list[int] = []
    for row in get_customer_list_aura():
        name = str(row.get("name", "")).strip().lower()
        if name == prefix or name.startswith(prefix + "_"):
            cid = row.get("id")
            try:
                ids.append(int(cid))
            except (TypeError, ValueError):
                continue
    return sorted(set(ids))


def resolve_customer_id(customer_name: str) -> Optional[int]:
    ids = resolve_customer_ids(customer_name)
    return ids[0] if ids else None


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
        "customer_ids": [],
    }
    cids = resolve_customer_ids(customer_name)
    if not cids:
        return empty
    svc_events: list[Any] = []
    vm_events: list[Any] = []
    for cid in cids:
        svc_body = get_customer_downtimes(cid, start_date, "service")
        vm_body = get_customer_downtimes(cid, start_date, "vm")
        se = svc_body.get("datacenter_downtimes") or []
        ve = vm_body.get("datacenter_downtimes") or []
        if isinstance(se, list):
            svc_events.extend(se)
        if isinstance(ve, list):
            vm_events.extend(ve)
    return {
        "service_downtimes": svc_events,
        "vm_downtimes": vm_events,
        "vm_outage_counts": vm_outage_counts_from_events(vm_events),
        "customer_id": cids[0],
        "customer_ids": cids,
    }
