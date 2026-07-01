import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from typing import Any, Callable, Literal, Optional, TypedDict
from urllib.parse import quote, urlencode

import httpx

from src.services import cache_service as _api_response_cache

logger = logging.getLogger(__name__)

# Microservices: set per-service URLs, or use API_BASE_URL for a single gateway.
_API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
DATACENTER_API_URL = os.getenv("DATACENTER_API_URL", _API_BASE).rstrip("/")
CUSTOMER_API_URL = os.getenv("CUSTOMER_API_URL", _API_BASE).rstrip("/")
QUERY_API_URL = os.getenv("QUERY_API_URL", _API_BASE).rstrip("/")
# crm-engine hosts /api/v1/crm/* (sellable, panels, ratios, conversions,
# config, service-mapping, metric-tags). Falls back to CUSTOMER_API_URL for
# legacy single-binary deployments that still serve those routes.
CRM_ENGINE_URL = os.getenv("CRM_ENGINE_URL", CUSTOMER_API_URL).rstrip("/")
HMDL_API_URL = os.getenv("HMDL_API_URL", "http://localhost:8007").rstrip("/")

_EMPTY_DASHBOARD = {
    "overview": {
        "dc_count": 0,
        "total_hosts": 0,
        "total_vms": 0,
        "total_platforms": 0,
        "total_energy_kw": 0.0,
        "total_cpu_cap": 0.0,
        "total_cpu_used": 0.0,
        "total_ram_cap": 0.0,
        "total_ram_used": 0.0,
        "total_storage_cap": 0.0,
        "total_storage_used": 0.0,
    },
    "platforms": {
        "nutanix": {"hosts": 0, "vms": 0},
        "vmware": {"clusters": 0, "hosts": 0, "vms": 0},
        "ibm": {"hosts": 0, "vios": 0, "lpars": 0},
    },
    "energy_breakdown": {"ibm_kw": 0.0, "vcenter_kw": 0.0},
    "classic_totals": {
        "cpu_cap": 0.0,
        "cpu_used": 0.0,
        "mem_cap": 0.0,
        "mem_used": 0.0,
        "stor_cap": 0.0,
        "stor_used": 0.0,
    },
    "hyperconv_totals": {
        "cpu_cap": 0.0,
        "cpu_used": 0.0,
        "mem_cap": 0.0,
        "mem_used": 0.0,
        "stor_cap": 0.0,
        "stor_used": 0.0,
    },
    "ibm_totals": {
        "mem_total": 0.0,
        "mem_assigned": 0.0,
        "cpu_used": 0.0,
        "cpu_assigned": 0.0,
        "stor_cap": 0.0,
        "stor_used": 0.0,
    },
}

_EMPTY_DC_DETAIL = {
    "meta": {"name": "", "location": "", "description": ""},
    "intel": {
        "clusters": 0,
        "hosts": 0,
        "vms": 0,
        "cpu_cap": 0.0,
        "cpu_used": 0.0,
        "ram_cap": 0.0,
        "ram_used": 0.0,
        "storage_cap": 0.0,
        "storage_used": 0.0,
    },
    "power": {
        "hosts": 0,
        "vms": 0,
        "vios": 0,
        "lpar_count": 0,
        "cpu": 0,
        "cpu_used": 0.0,
        "cpu_assigned": 0.0,
        "ram": 0,
        "memory_total": 0.0,
        "memory_assigned": 0.0,
        "storage_cap_tb": 0.0,
        "storage_used_tb": 0.0,
    },
    "energy": {
        "total_kw": 0.0,
        "ibm_kw": 0.0,
        "vcenter_kw": 0.0,
        "total_kwh": 0.0,
        "ibm_kwh": 0.0,
        "vcenter_kwh": 0.0,
    },
    "platforms": {
        "nutanix": {"hosts": 0, "vms": 0},
        "vmware": {"clusters": 0, "hosts": 0, "vms": 0},
        "ibm": {"hosts": 0, "vios": 0, "lpars": 0},
    },
}

_EMPTY_CUSTOMER = {"totals": {}, "assets": {}}
_EMPTY_QUERY = {"error": "API unreachable"}
_EMPTY_DATACENTERS: list[dict[str, Any]] = []
_EMPTY_CUSTOMERS: list[str] = []
_EMPTY_CATALOG_GROUPS: dict[str, list] = {"vip": [], "mapped": [], "unmapped": []}
_EMPTY_SLA_BY_DC: dict[str, dict] = {}


def _empty_catalog(*, load_error: bool = False) -> dict[str, Any]:
    return {
        "customers": [],
        "groups": deepcopy(_EMPTY_CATALOG_GROUPS),
        "degraded": load_error,
        "_load_error": load_error,
    }

_HTTP_TLS = threading.local()

# Single-flight coalescing: concurrent cache misses for the SAME key share one fetch.
# The lock is held ONLY for the tiny dict operations, never while fetch_normalized() runs.
_inflight_lock = threading.Lock()
_inflight: dict[str, threading.Event] = {}

# Stale-while-revalidate (SWR): timestamps tracked ONLY for entries fetched by the leader
# path below. Warm-job entries (written directly via cache_service.set) have NO entry here
# and are therefore NEVER auto-refreshed (avoids conflict with warm jobs).
_SWR_TTL_SECONDS = float(os.getenv("API_CACHE_SWR_TTL", "300") or "300")
_fetched_at: dict[str, float] = {}
_swr_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="api-swr")
_swr_refreshing_lock = threading.Lock()
_swr_refreshing: set[str] = set()

# httpx.Client is not safe to share across threads; background prefetch uses thread pools.
# One client (+ transport pool) per thread avoids cross-thread contention and 30s read timeouts.


def _new_http_transport() -> httpx.HTTPTransport:
    return httpx.HTTPTransport(retries=3)


# Read timeout sized to let genuinely-slow cold queries (filtered compute is 15-39s
# over the remote VPN DB) COMPLETE and populate the cache, instead of timing out at
# 8s and returning empty — which never caches, so warm==cold and the UI shows zeros.
# Connect stays short so a truly-unreachable backend still fails fast. Tunable via env.
_INTERACTIVE_READ_TIMEOUT = float(os.getenv("API_INTERACTIVE_READ_TIMEOUT", "20") or "20")
_INFLIGHT_WAIT_SECONDS = float(os.getenv("API_INFLIGHT_WAIT_SECONDS", "0") or "0")
if _INFLIGHT_WAIT_SECONDS <= 0:
    _INFLIGHT_WAIT_SECONDS = max(25.0, _INTERACTIVE_READ_TIMEOUT + 5.0)
_INTERACTIVE_TIMEOUT = httpx.Timeout(
    _INTERACTIVE_READ_TIMEOUT, connect=5.0, read=_INTERACTIVE_READ_TIMEOUT,
    write=_INTERACTIVE_READ_TIMEOUT, pool=5.0,
)
_INVENTORY_READ_TIMEOUT = float(os.getenv("API_INVENTORY_READ_TIMEOUT", "300") or "300")
_INVENTORY_TIMEOUT = httpx.Timeout(
    _INVENTORY_READ_TIMEOUT, connect=10.0, read=_INVENTORY_READ_TIMEOUT,
    write=_INVENTORY_READ_TIMEOUT, pool=10.0,
)


def _get_client_dc() -> httpx.Client:
    c = getattr(_HTTP_TLS, "dc", None)
    if c is None:
        _HTTP_TLS.dc = httpx.Client(
            base_url=DATACENTER_API_URL, timeout=_INTERACTIVE_TIMEOUT, transport=_new_http_transport()
        )
        c = _HTTP_TLS.dc
    return c


def _get_client_cust() -> httpx.Client:
    c = getattr(_HTTP_TLS, "cust", None)
    if c is None:
        _HTTP_TLS.cust = httpx.Client(
            base_url=CUSTOMER_API_URL, timeout=_INTERACTIVE_TIMEOUT, transport=_new_http_transport()
        )
        c = _HTTP_TLS.cust
    return c


def _get_client_query() -> httpx.Client:
    c = getattr(_HTTP_TLS, "query", None)
    if c is None:
        _HTTP_TLS.query = httpx.Client(
            base_url=QUERY_API_URL, timeout=_INTERACTIVE_TIMEOUT, transport=_new_http_transport()
        )
        c = _HTTP_TLS.query
    return c


def _get_client_hmdl() -> httpx.Client:
    c = getattr(_HTTP_TLS, "hmdl", None)
    if c is None:
        _HTTP_TLS.hmdl = httpx.Client(
            base_url=HMDL_API_URL, timeout=_INTERACTIVE_TIMEOUT, transport=_new_http_transport()
        )
        c = _HTTP_TLS.hmdl
    return c


def _get_client_crm() -> httpx.Client:
    c = getattr(_HTTP_TLS, "crm", None)
    if c is None:
        _HTTP_TLS.crm = httpx.Client(
            base_url=CRM_ENGINE_URL, timeout=_INTERACTIVE_TIMEOUT, transport=_new_http_transport()
        )
        c = _HTTP_TLS.crm
    return c


def _clone(value: Any) -> Any:
    return deepcopy(value)


def _build_time_params(tr: Optional[dict]) -> dict[str, str]:
    if not tr:
        return {}
    params: dict[str, str] = {}
    preset = tr.get("preset")
    if preset in {"1h", "1d", "7d", "30d"}:
        params["preset"] = preset
    else:
        start = tr.get("start")
        end = tr.get("end")
        if start and end:
            params["start"] = str(start)
            params["end"] = str(end)
    if tr.get("anchor_latest"):
        params["anchor_latest"] = "true"
    return params


def _auth_headers() -> dict[str, str]:
    """Attach JWT for microservices when Flask request has an authenticated user."""
    try:
        from flask import g, has_request_context

        if has_request_context():
            uid = getattr(g, "auth_user_id", None)
            if uid is not None:
                from src.auth.api_jwt import create_api_token

                tok = create_api_token(int(uid))
                return {"Authorization": f"Bearer {tok}"}
    except Exception:
        pass
    return {}


def _get_json(client: httpx.Client, path: str, params: Optional[dict[str, str]] = None) -> Any:
    response = client.get(path, params=params, headers=_auth_headers())
    response.raise_for_status()
    return response.json()


def _put_json(client: httpx.Client, path: str, body: dict[str, Any]) -> Any:
    response = client.put(path, json=body, headers=_auth_headers())
    response.raise_for_status()
    return response.json()


def _post_json(client: httpx.Client, path: str, body: dict[str, Any] | None = None) -> Any:
    response = client.post(path, json=body or {}, headers=_auth_headers())
    response.raise_for_status()
    if not response.content:
        return {}
    return response.json()


def _delete_json(client: httpx.Client, path: str) -> Any:
    response = client.delete(path, headers=_auth_headers())
    response.raise_for_status()
    if not response.content:
        return {}
    return response.json()


def _sellable_panels_have_data(panels: list) -> bool:
    """True when at least one panel row carries infra-backed or non-zero potential."""
    for p in panels:
        if not isinstance(p, dict):
            continue
        if p.get("has_infra_source"):
            return True
        if float(p.get("potential_tl") or 0.0) > 0:
            return True
    return False


def _sellable_summary_has_data(summary: dict) -> bool:
    if not isinstance(summary, dict):
        return False
    if float(summary.get("total_potential_tl") or 0.0) > 0:
        return True
    for fam in summary.get("families") or []:
        if not isinstance(fam, dict):
            continue
        if float(fam.get("total_potential_tl") or 0.0) > 0:
            return True
        for p in fam.get("panels") or []:
            if isinstance(p, dict) and (
                p.get("has_infra_source") or float(p.get("potential_tl") or 0.0) > 0
            ):
                return True
    return False


def get_sellable_snapshot_meta(
    dc_code: str = "*",
    family: Optional[str] = None,
    clusters: Optional[list[str]] = None,
) -> dict[str, Any]:
    qs = f"dc_code={quote(dc_code, safe='*')}"
    if family:
        qs += f"&family={quote(family, safe='')}"
    cl = _normalize_clusters_arg(clusters)
    if cl:
        qs += f"&clusters={quote(','.join(cl), safe=',')}"

    def fetch() -> dict[str, Any]:
        data = _get_json(_get_client_crm(), f"/api/v1/crm/sellable-potential/snapshot-meta?{qs}")
        return data if isinstance(data, dict) else {}

    cache_key = f"api:sellable_snapshot_meta:{dc_code}:{family or '*'}:{','.join(cl) if cl else '*'}"
    return _api_cache_get_with_stale(cache_key, fetch, {})


def refresh_sellable_potential() -> dict[str, Any]:
    out = _post_json(_get_client_crm(), "/api/v1/crm/sellable-potential/refresh")
    _invalidate_sellable_caches()
    return out if isinstance(out, dict) else {}


def _api_cache_get_sellable_panels(
    cache_key: str,
    fetch_normalized: Callable[[], list],
    dc_code: str,
    family: Optional[str],
    clusters: Optional[list[str]],
) -> list:
    """Cache sellable panels (even empty) with stale-while-revalidate, so DCs without a
    snapshot don't re-pay the CRM round-trip on every build. Transient empties self-heal
    via the SWR background refresh after _SWR_TTL_SECONDS."""
    stale = _api_response_cache.get(cache_key)
    if stale is not None:
        if _SWR_TTL_SECONDS > 0:
            age = _swr_age(cache_key)
            if age is not None and age > _SWR_TTL_SECONDS:
                _schedule_swr_refresh(cache_key, fetch_normalized)
        return _clone(stale)
    try:
        out = fetch_normalized()
        _api_response_cache.set(cache_key, out)
        _fetched_at[cache_key] = time.monotonic()
        return out
    except _HTTP_ERRORS:
        hit = _api_response_cache.get(cache_key)
        if hit is not None:
            return _clone(hit)
        return []


def _api_cache_get_sellable_summary(
    cache_key: str,
    fetch_normalized: Callable[[], dict],
    dc_code: str,
) -> dict:
    """Cache sellable summary (even empty) with stale-while-revalidate, so DCs without a
    snapshot don't re-pay the CRM round-trip on every build. Transient empties self-heal
    via the SWR background refresh after _SWR_TTL_SECONDS."""
    stale = _api_response_cache.get(cache_key)
    if stale is not None:
        if _SWR_TTL_SECONDS > 0:
            age = _swr_age(cache_key)
            if age is not None and age > _SWR_TTL_SECONDS:
                _schedule_swr_refresh(cache_key, fetch_normalized)
        return _clone(stale)
    try:
        out = fetch_normalized()
        _api_response_cache.set(cache_key, out)
        _fetched_at[cache_key] = time.monotonic()
        return out
    except _HTTP_ERRORS:
        hit = _api_response_cache.get(cache_key)
        if hit is not None:
            return _clone(hit)
        return {}


_HTTP_ERRORS = (
    httpx.ConnectError,
    httpx.TimeoutException,
    httpx.HTTPStatusError,
    httpx.RemoteProtocolError,
    ValueError,
)


def _serialize_tr_params(tr: Optional[dict]) -> str:
    p = _build_time_params(tr)
    if not p:
        return "noparams"
    return json.dumps(sorted(p.items()), separators=(",", ":"), ensure_ascii=False)


def _swr_age(cache_key: str) -> Optional[float]:
    """Return age (seconds) of this key's last leader-fetch, or None if no timestamp exists."""
    ts = _fetched_at.get(cache_key)
    return None if ts is None else (time.monotonic() - ts)


def _schedule_swr_refresh(cache_key: str, fetch_normalized: Callable[[], Any]) -> None:
    """Background single-flight refresh of a stale entry. Errors swallowed (keep serving stale)."""
    with _swr_refreshing_lock:
        if cache_key in _swr_refreshing:
            return
        _swr_refreshing.add(cache_key)

    def _refresh() -> None:
        try:
            out = fetch_normalized()
            _api_response_cache.set(cache_key, out)
            _fetched_at[cache_key] = time.monotonic()
        except _HTTP_ERRORS:
            pass
        finally:
            with _swr_refreshing_lock:
                _swr_refreshing.discard(cache_key)

    _swr_executor.submit(_refresh)


def _serialize_tr_cache_key(tr: Optional[dict]) -> str:
    """Cache keys include resolved start/end so rolling presets invalidate correctly."""
    if not tr:
        return "noparams"
    parts: list[tuple[str, str]] = []
    for key in ("start", "end", "preset"):
        val = tr.get(key)
        if val not in (None, ""):
            parts.append((key, str(val)))
    if tr.get("anchor_latest"):
        parts.append(("anchor_latest", "true"))
    if not parts:
        return "noparams"
    return json.dumps(sorted(parts), separators=(",", ":"), ensure_ascii=False)


def _should_persist_api_cache(value: Any, empty_fallback: Any) -> bool:
    if value == empty_fallback:
        return False
    if isinstance(value, dict) and not value:
        return False
    if isinstance(value, dict) and value.get("totals") == {} and value.get("assets") == {}:
        return False
    if isinstance(value, list) and not value:
        return False
    return True



def _api_cache_get_with_stale(
    cache_key: str,
    fetch_normalized: Callable[[], Any],
    empty_fallback: Any,
) -> Any:
    """Cached payload if present; else single-flight fetch (concurrent callers share one fetch).
    On cache HIT, if the entry is older than _SWR_TTL_SECONDS, a background refresh is scheduled
    (stale-while-revalidate) — the caller always receives the cached value immediately without
    blocking. On HTTP/transport errors return last-good payload."""
    stale = _api_response_cache.get(cache_key)
    if stale is not None:
        if _SWR_TTL_SECONDS > 0:
            age = _swr_age(cache_key)
            if age is not None and age > _SWR_TTL_SECONDS:
                _schedule_swr_refresh(cache_key, fetch_normalized)
        return _clone(stale)

    with _inflight_lock:
        ev = _inflight.get(cache_key)
        leader = ev is None
        if leader:
            ev = threading.Event()
            _inflight[cache_key] = ev
    if not leader:
        ev.wait(timeout=_INFLIGHT_WAIT_SECONDS)
        hit = _api_response_cache.get(cache_key)
        return _clone(hit) if hit is not None else _clone(empty_fallback)

    try:
        out = fetch_normalized()
        if _should_persist_api_cache(out, empty_fallback):
            _api_response_cache.set(cache_key, out)
            _fetched_at[cache_key] = time.monotonic()
        return out
    except _HTTP_ERRORS as exc:
        logger.warning("API cache fetch failed for key=%s: %s", cache_key, exc)
        hit = _api_response_cache.get(cache_key)
        if hit is not None:
            return _clone(hit)
        return _clone(empty_fallback)
    finally:
        with _inflight_lock:
            _inflight.pop(cache_key, None)
        ev.set()


def get_global_dashboard(tr: Optional[dict]) -> dict:
    ck = f"api:global_dashboard:{_serialize_tr_cache_key(tr)}"

    def fetch() -> dict:
        data = _get_json(_get_client_dc(), "/api/v1/dashboard/overview", params=_build_time_params(tr))
        return data if isinstance(data, dict) else _clone(_EMPTY_DASHBOARD)

    return _api_cache_get_with_stale(ck, fetch, _EMPTY_DASHBOARD)


def get_all_datacenters_summary(tr: Optional[dict]) -> list[dict]:
    ck = f"api:datacenters_summary:{_serialize_tr_cache_key(tr)}"

    def fetch() -> list[dict]:
        params = _build_time_params(tr)
        data = _get_json(_get_client_dc(), "/api/v1/datacenters/summary", params=params)
        return data if isinstance(data, list) else _clone(_EMPTY_DATACENTERS)

    return _api_cache_get_with_stale(ck, fetch, _EMPTY_DATACENTERS)


def get_dc_details(dc_id: str, tr: Optional[dict]) -> dict:
    enc = quote(dc_id, safe="")
    ck = f"api:dc_details:{enc}:{_serialize_tr_cache_key(tr)}"

    def fetch() -> dict:
        data = _get_json(_get_client_dc(), f"/api/v1/datacenters/{enc}", params=_build_time_params(tr))
        return data if isinstance(data, dict) else _clone(_EMPTY_DC_DETAIL)

    return _api_cache_get_with_stale(ck, fetch, _EMPTY_DC_DETAIL)


def get_customer_list() -> list[str]:
    ck = "api:customer_list"

    def fetch() -> list[str]:
        data = _get_json(_get_client_cust(), "/api/v1/customers")
        return data if isinstance(data, list) else _clone(_EMPTY_CUSTOMERS)

    return _api_cache_get_with_stale(ck, fetch, _EMPTY_CUSTOMERS)


def get_customer_catalog() -> dict[str, Any]:
    ck = "api:customer_catalog"

    def fetch() -> dict[str, Any]:
        data = _get_json(_get_client_cust(), "/api/v1/customers/catalog")
        return data if isinstance(data, dict) else _empty_catalog()

    return _api_cache_get_with_stale(ck, fetch, _empty_catalog())


def get_customer_overview() -> dict[str, Any]:
    ck = "api:customer_overview"

    def fetch() -> dict[str, Any]:
        data = _get_json(_get_client_cust(), "/api/v1/customers/overview")
        return data if isinstance(data, dict) else {}

    return _api_cache_get_with_stale(ck, fetch, {})


def get_customers_page_data() -> dict[str, Any]:
    """Single overview fetch; catalog is embedded by customer-api to avoid duplicate builds."""
    overview = get_customer_overview() or {}
    catalog = overview.get("catalog") if isinstance(overview.get("catalog"), dict) else {}
    if not catalog.get("customers"):
        catalog = get_customer_catalog() or _empty_catalog()
    customers = catalog.get("customers") if isinstance(catalog.get("customers"), list) else []
    groups = catalog.get("groups") if isinstance(catalog.get("groups"), dict) else deepcopy(_EMPTY_CATALOG_GROUPS)
    if not groups and customers:
        groups = deepcopy(_EMPTY_CATALOG_GROUPS)
        for row in customers:
            group = str(row.get("list_group") or "unmapped")
            groups.setdefault(group, []).append(row)
    load_error = bool(
        catalog.get("_load_error")
        or (not customers and not overview.get("total_customers"))
    )
    degraded = bool(catalog.get("degraded") or catalog.get("prj_query_failed"))
    return {
        "customers": customers,
        "groups": groups,
        "overview": overview if isinstance(overview, dict) else {},
        "load_error": load_error,
        "degraded": degraded,
    }


def _crm_aliases_response_cacheable(rows: list) -> bool:
    if not rows:
        return False
    if len(rows) == 1:
        name = str((rows[0] or {}).get("crm_account_name") or "").lower()
        if "boyner" in name:
            return False
    return True


def set_customer_vip(crm_accountid: str, *, is_vip: bool) -> dict[str, Any]:
    enc = quote(crm_accountid, safe="")
    out = _put_json(
        _get_client_cust(),
        f"/api/v1/customers/{enc}/vip",
        {"is_vip": bool(is_vip)},
    )
    _api_response_cache.delete("api:customer_catalog")
    _api_response_cache.delete("api:customer_overview")
    return out if isinstance(out, dict) else {}


def get_customer_resources(name: str, tr: Optional[dict]) -> dict:
    enc = quote(name, safe="")
    ck = f"api:customer_resources:cpu-usage-v3:{enc}:{_serialize_tr_cache_key(tr)}"

    def fetch() -> dict:
        data = _get_json(
            _get_client_cust(),
            f"/api/v1/customers/{enc}/resources",
            params=_build_time_params(tr),
        )
        return data if isinstance(data, dict) else _clone(_EMPTY_CUSTOMER)

    return _api_cache_get_with_stale(ck, fetch, _EMPTY_CUSTOMER)


def execute_registered_query(key: str, params: str) -> dict:
    enc_key = quote(key, safe="")
    ck = f"api:query:{enc_key}:{json.dumps(params or '', ensure_ascii=False)}"

    def fetch() -> dict:
        data = _get_json(_get_client_query(), f"/api/v1/queries/{enc_key}", params={"params": params or ""})
        return data if isinstance(data, dict) else _clone(_EMPTY_QUERY)

    return _api_cache_get_with_stale(ck, fetch, _EMPTY_QUERY)


def get_sla_by_dc(tr: Optional[dict]) -> dict[str, dict]:
    """Return SLA entries keyed by DC code (uppercase)."""
    ck = f"api:sla_by_dc:{_serialize_tr_cache_key(tr)}"

    def fetch() -> dict[str, dict]:
        data = _get_json(_get_client_dc(), "/api/v1/sla", params=_build_time_params(tr))
        by_dc = (data or {}).get("by_dc") if isinstance(data, dict) else None
        return by_dc if isinstance(by_dc, dict) else _clone(_EMPTY_SLA_BY_DC)

    return _api_cache_get_with_stale(ck, fetch, _EMPTY_SLA_BY_DC)


def get_dc_s3_pools(dc_code: str, tr: Optional[dict]) -> dict:
    enc = quote(dc_code, safe="")
    empty = {"pools": [], "latest": {}, "growth": {}}
    ck = f"api:dc_s3_pools:{enc}:{_serialize_tr_cache_key(tr)}"

    def fetch() -> dict:
        data = _get_json(_get_client_dc(), f"/api/v1/datacenters/{enc}/s3/pools", params=_build_time_params(tr))
        return data if isinstance(data, dict) else empty

    return _api_cache_get_with_stale(ck, fetch, empty)


def get_customer_s3_vaults(customer_name: str, tr: Optional[dict]) -> dict:
    enc = quote(customer_name, safe="")
    empty = {"vaults": [], "latest": {}, "growth": {}}
    ck = f"api:customer_s3_vaults:{enc}:{_serialize_tr_cache_key(tr)}"

    def fetch() -> dict:
        data = _get_json(_get_client_cust(), f"/api/v1/customers/{enc}/s3/vaults", params=_build_time_params(tr))
        return data if isinstance(data, dict) else empty

    return _api_cache_get_with_stale(ck, fetch, empty)


# ---------------------------------------------------------------------------
# ITSM (ServiceCore) — customer incident + service request metrics
# ---------------------------------------------------------------------------

_EMPTY_ITSM_SUMMARY: dict = {
    "total_count": 0, "incident_count": 0, "sr_count": 0,
    "incident_open": 0, "incident_closed": 0, "sr_open": 0, "sr_closed": 0,
    "avg_resolution_hours": None, "median_resolution_hours": None,
    "p95_resolution_hours": None, "stddev_resolution_hours": None,
    "sla_breach_count": 0, "top_category": None,
    "priority_distribution": [], "state_distribution": [],
}

_EMPTY_ITSM_EXTREMES: dict = {"long_tail": [], "sla_breach": []}


def get_customer_itsm_summary(customer_name: str, tr: Optional[dict]) -> dict:
    enc = quote(customer_name, safe="")
    ck = f"api:customer_itsm_summary:{enc}:{_serialize_tr_cache_key(tr)}"

    def fetch() -> dict:
        data = _get_json(_get_client_cust(), f"/api/v1/customers/{enc}/itsm/summary", params=_build_time_params(tr))
        return data if isinstance(data, dict) else _EMPTY_ITSM_SUMMARY

    return _api_cache_get_with_stale(ck, fetch, _EMPTY_ITSM_SUMMARY)


def get_customer_itsm_extremes(customer_name: str, tr: Optional[dict]) -> dict:
    enc = quote(customer_name, safe="")
    ck = f"api:customer_itsm_extremes:{enc}:{_serialize_tr_cache_key(tr)}"

    def fetch() -> dict:
        data = _get_json(_get_client_cust(), f"/api/v1/customers/{enc}/itsm/extremes", params=_build_time_params(tr))
        return data if isinstance(data, dict) else _EMPTY_ITSM_EXTREMES

    return _api_cache_get_with_stale(ck, fetch, _EMPTY_ITSM_EXTREMES)


def get_customer_itsm_tickets(customer_name: str, tr: Optional[dict]) -> list:
    enc = quote(customer_name, safe="")
    ck = f"api:customer_itsm_tickets:{enc}:{_serialize_tr_cache_key(tr)}"

    def fetch() -> list:
        data = _get_json(_get_client_cust(), f"/api/v1/customers/{enc}/itsm/tickets", params=_build_time_params(tr))
        return data if isinstance(data, list) else []

    return _api_cache_get_with_stale(ck, fetch, [])


def get_dc_netbackup_pools(dc_code: str, tr: Optional[dict]) -> dict:
    enc = quote(dc_code, safe="")
    empty = {"pools": [], "rows": []}
    ck = f"api:dc_netbackup:{enc}:{_serialize_tr_cache_key(tr)}"

    def fetch() -> dict:
        data = _get_json(_get_client_dc(), f"/api/v1/datacenters/{enc}/backup/netbackup", params=_build_time_params(tr))
        return data if isinstance(data, dict) else empty

    return _api_cache_get_with_stale(ck, fetch, empty)


def get_dc_zerto_sites(dc_code: str, tr: Optional[dict]) -> dict:
    enc = quote(dc_code, safe="")
    empty = {"sites": [], "rows": []}
    ck = f"api:dc_zerto:{enc}:{_serialize_tr_cache_key(tr)}"

    def fetch() -> dict:
        data = _get_json(_get_client_dc(), f"/api/v1/datacenters/{enc}/backup/zerto", params=_build_time_params(tr))
        return data if isinstance(data, dict) else empty

    return _api_cache_get_with_stale(ck, fetch, empty)


def get_dc_veeam_repos(dc_code: str, tr: Optional[dict]) -> dict:
    enc = quote(dc_code, safe="")
    empty = {"repos": [], "rows": []}
    ck = f"api:dc_veeam:{enc}:{_serialize_tr_cache_key(tr)}"

    def fetch() -> dict:
        data = _get_json(_get_client_dc(), f"/api/v1/datacenters/{enc}/backup/veeam", params=_build_time_params(tr))
        return data if isinstance(data, dict) else empty

    return _api_cache_get_with_stale(ck, fetch, empty)


def _empty_job_stats(vendor: str, granularity: str) -> dict:
    return {
        "vendor": vendor,
        "granularity": granularity,
        "range": {"start": "", "end": ""},
        "series": [],
        "totals": {
            "total": 0, "success": 0, "failed": 0, "warning": 0, "other": 0,
            "success_rate": 0.0, "avg_per_period": 0.0, "period_count": 0,
        },
    }


def get_dc_veeam_jobs(dc_code: str, tr: Optional[dict], granularity: str = "day") -> dict:
    enc = quote(dc_code, safe="")
    empty = _empty_job_stats("veeam", granularity)
    ck = f"api:dc_veeam_jobs:{enc}:{_serialize_tr_cache_key(tr)}:{granularity}"

    def fetch() -> dict:
        params = {**_build_time_params(tr), "granularity": granularity}
        data = _get_json(_get_client_dc(), f"/api/v1/datacenters/{enc}/backup/veeam/jobs", params=params)
        return data if isinstance(data, dict) else empty

    return _api_cache_get_with_stale(ck, fetch, empty)


def get_dc_zerto_jobs(dc_code: str, tr: Optional[dict], granularity: str = "day") -> dict:
    enc = quote(dc_code, safe="")
    empty = _empty_job_stats("zerto", granularity)
    ck = f"api:dc_zerto_jobs:{enc}:{_serialize_tr_cache_key(tr)}:{granularity}"

    def fetch() -> dict:
        params = {**_build_time_params(tr), "granularity": granularity}
        data = _get_json(_get_client_dc(), f"/api/v1/datacenters/{enc}/backup/zerto/jobs", params=params)
        return data if isinstance(data, dict) else empty

    return _api_cache_get_with_stale(ck, fetch, empty)


def get_dc_netbackup_jobs(dc_code: str, tr: Optional[dict], granularity: str = "day") -> dict:
    enc = quote(dc_code, safe="")
    empty = _empty_job_stats("netbackup", granularity)
    ck = f"api:dc_netbackup_jobs:{enc}:{_serialize_tr_cache_key(tr)}:{granularity}"

    def fetch() -> dict:
        params = {**_build_time_params(tr), "granularity": granularity}
        data = _get_json(_get_client_dc(), f"/api/v1/datacenters/{enc}/backup/netbackup/jobs", params=params)
        return data if isinstance(data, dict) else empty

    return _api_cache_get_with_stale(ck, fetch, empty)


def refresh_dc_backup_jobs_cache(dc_code: str, vendor: str = "all") -> dict:
    """
    Force backend cache invalidation for a DC's job stats (single vendor or all).

    Also flushes the GUI-side wrapper memory cache for the affected wrappers so
    the next read goes through the HTTP layer (and hits a now-empty backend
    cache, which then performs a live SQL run).
    """
    enc = quote(dc_code, safe="")
    try:
        client = _get_client_dc()
        resp = client.post(
            f"/api/v1/datacenters/{enc}/backup/jobs/refresh",
            params={"vendor": vendor},
            headers=_auth_headers(),
            timeout=10.0,
        )
        resp.raise_for_status()
        payload = resp.json() if resp.content else {"status": "ok"}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}

    # Also drop GUI-side wrapper cache so re-fetch is forced.
    vendors = ("veeam", "zerto", "netbackup") if vendor == "all" else (vendor,)
    from src.services import cache_service as cs

    for v in vendors:
        if v not in ("veeam", "zerto", "netbackup"):
            continue
        try:
            cs.delete_prefix(f"api:dc_{v}_jobs:{enc}:")
        except AttributeError:
            # Older cache_service may lack delete_prefix; clear() is a coarser
            # fallback but acceptable for a manual refresh action.
            try:
                cs.clear()
            except Exception:
                pass

    return payload if isinstance(payload, dict) else {"status": "ok"}


def get_classic_cluster_list(dc_code: str, tr: Optional[dict]) -> list[str]:
    enc = quote(dc_code, safe="")
    ck = f"api:classic_clusters:{enc}:{_serialize_tr_cache_key(tr)}"

    def fetch() -> list[str]:
        data = _get_json(_get_client_dc(), f"/api/v1/datacenters/{enc}/clusters/classic", params=_build_time_params(tr))
        return data if isinstance(data, list) else []

    return _api_cache_get_with_stale(ck, fetch, [])


def get_hyperconv_cluster_list(dc_code: str, tr: Optional[dict]) -> list[str]:
    enc = quote(dc_code, safe="")
    ck = f"api:hyperconv_clusters:{enc}:{_serialize_tr_cache_key(tr)}"

    def fetch() -> list[str]:
        data = _get_json(
            _get_client_dc(),
            f"/api/v1/datacenters/{enc}/clusters/hyperconverged",
            params=_build_time_params(tr),
        )
        return data if isinstance(data, list) else []

    return _api_cache_get_with_stale(ck, fetch, [])


def _clusters_param(selected: Optional[list[str]]) -> dict[str, str]:
    if not selected:
        return {}
    return {"clusters": ",".join(selected)}


def get_classic_metrics_filtered(
    dc_code: str, selected_clusters: Optional[list[str]], tr: Optional[dict]
) -> dict:
    enc = quote(dc_code, safe="")
    params = {**_build_time_params(tr), **_clusters_param(selected_clusters)}
    ck = f"api:classic_metrics:{enc}:{json.dumps(sorted(params.items()), separators=(',', ':'))}"

    def fetch() -> dict:
        data = _get_json(_get_client_dc(), f"/api/v1/datacenters/{enc}/compute/classic", params=params)
        return data if isinstance(data, dict) else {}

    return _api_cache_get_with_stale(ck, fetch, {})


def get_hyperconv_metrics_filtered(
    dc_code: str, selected_clusters: Optional[list[str]], tr: Optional[dict]
) -> dict:
    enc = quote(dc_code, safe="")
    params = {**_build_time_params(tr), **_clusters_param(selected_clusters)}
    ck = f"api:hyperconv_metrics:{enc}:{json.dumps(sorted(params.items()), separators=(',', ':'))}"

    def fetch() -> dict:
        data = _get_json(_get_client_dc(), f"/api/v1/datacenters/{enc}/compute/hyperconverged", params=params)
        return data if isinstance(data, dict) else {}

    return _api_cache_get_with_stale(ck, fetch, {})


from shared.sellable.host_aggregate import finalize_host_payload


def _slice_host_rows(full: dict, selected_clusters: Optional[list[str]]) -> dict:
    """Filter host rows to selected clusters (None/empty => all). Rows are self-contained."""
    hosts = (full or {}).get("hosts") or []
    if not selected_clusters:
        return finalize_host_payload({"hosts": list(hosts), "host_count": len(hosts)})
    wanted = set(selected_clusters)
    filtered = [h for h in hosts if h.get("cluster") in wanted]
    return finalize_host_payload({"hosts": filtered, "host_count": len(filtered)})


def get_classic_host_rows(
    dc_code: str, selected_clusters: Optional[list[str]], tr: Optional[dict]
) -> dict:
    """Per-host compute rows for Classic (KM). Full DC list fetched once (cached);
    cluster subset is sliced in-process so toggling clusters is a cache hit."""
    enc = quote(dc_code, safe="")
    params = _build_time_params(tr)  # NO clusters -> one cache entry per dc/time
    ck = f"api:classic_hosts_all:{enc}:{json.dumps(sorted(params.items()), separators=(',', ':'))}"

    def fetch() -> dict:
        data = _get_json(_get_client_dc(), f"/api/v1/datacenters/{enc}/compute/classic/hosts", params=params)
        return data if isinstance(data, dict) else {"hosts": [], "host_count": 0}

    full = _api_cache_get_with_stale(ck, fetch, {"hosts": [], "host_count": 0})
    return _slice_host_rows(full, selected_clusters)


def get_hyperconv_host_rows(
    dc_code: str, selected_clusters: Optional[list[str]], tr: Optional[dict]
) -> dict:
    """Per-host compute rows for Hyperconverged (Nutanix). Full DC list fetched once (cached);
    cluster subset is sliced in-process so toggling clusters is a cache hit."""
    enc = quote(dc_code, safe="")
    params = _build_time_params(tr)  # NO clusters -> one cache entry per dc/time
    ck = f"api:hyperconv_hosts_all:{enc}:{json.dumps(sorted(params.items()), separators=(',', ':'))}"

    def fetch() -> dict:
        data = _get_json(_get_client_dc(), f"/api/v1/datacenters/{enc}/compute/hyperconverged/hosts", params=params)
        return data if isinstance(data, dict) else {"hosts": [], "host_count": 0}

    full = _api_cache_get_with_stale(ck, fetch, {"hosts": [], "host_count": 0})
    return _slice_host_rows(full, selected_clusters)


def get_physical_inventory_dc(dc_name: str) -> dict:
    enc = quote(dc_name, safe="")
    empty = {"total": 0, "by_role": [], "by_role_manufacturer": []}
    ck = f"api:phys_inv_dc:{enc}"

    def fetch() -> dict:
        data = _get_json(_get_client_dc(), f"/api/v1/datacenters/{enc}/physical-inventory")
        return data if isinstance(data, dict) else empty

    return _api_cache_get_with_stale(ck, fetch, empty)


def get_physical_inventory_overview_by_role() -> list[dict]:
    ck = "api:phys_inv_overview_by_role"

    def fetch() -> list[dict]:
        data = _get_json(_get_client_dc(), "/api/v1/physical-inventory/overview/by-role")
        return data if isinstance(data, list) else []

    return _api_cache_get_with_stale(ck, fetch, [])


def get_physical_inventory_overview_manufacturer(role: str) -> list[dict]:
    enc = quote(role, safe="")
    ck = f"api:phys_inv_mfr:{enc}"

    def fetch() -> list[dict]:
        data = _get_json(_get_client_dc(), "/api/v1/physical-inventory/overview/manufacturer", params={"role": enc})
        return data if isinstance(data, list) else []

    return _api_cache_get_with_stale(ck, fetch, [])


def get_physical_inventory_overview_location(role: str, manufacturer: str) -> list[dict]:
    ck = f"api:phys_inv_loc:{quote(role, safe='')}:{quote(manufacturer, safe='')}"

    def fetch() -> list[dict]:
        data = _get_json(
            _get_client_dc(),
            "/api/v1/physical-inventory/overview/location",
            params={"role": role, "manufacturer": manufacturer},
        )
        return data if isinstance(data, list) else []

    return _api_cache_get_with_stale(ck, fetch, [])


def get_physical_inventory_customer(customer_name: str | None = None) -> list[dict]:
    ck = f"api:phys_inv_customer:{(customer_name or '').strip().casefold()}"

    def fetch() -> list[dict]:
        params = {}
        if customer_name and str(customer_name).strip():
            params["customer"] = str(customer_name).strip()
        data = _get_json(
            _get_client_dc(),
            "/api/v1/physical-inventory/customer",
            params=params or None,
        )
        return data if isinstance(data, list) else []

    return _api_cache_get_with_stale(ck, fetch, [])


# ---------------------------------------------------------------------------
# Network > SAN (Brocade) + Power Mimari Storage (IBM)
# ---------------------------------------------------------------------------


def get_dc_san_switches(dc_code: str, tr: Optional[dict]) -> list[str]:
    enc = quote(dc_code, safe="")
    params = _build_time_params(tr)
    ck = f"api:dc_san_switches:{enc}:{_serialize_tr_cache_key(tr)}"

    def fetch() -> list[str]:
        data = _get_json(_get_client_dc(), f"/api/v1/datacenters/{enc}/san/switches", params=params)
        return data if isinstance(data, list) else []

    return _api_cache_get_with_stale(ck, fetch, [])


def get_dc_san_port_usage(dc_code: str, tr: Optional[dict]) -> dict:
    enc = quote(dc_code, safe="")
    params = _build_time_params(tr)
    ck = f"api:dc_san_port_usage:{enc}:{_serialize_tr_cache_key(tr)}"

    def fetch() -> dict:
        data = _get_json(_get_client_dc(), f"/api/v1/datacenters/{enc}/san/port-usage", params=params)
        return data if isinstance(data, dict) else {}

    return _api_cache_get_with_stale(ck, fetch, {})


def get_dc_san_health(dc_code: str, tr: Optional[dict]) -> list[dict]:
    enc = quote(dc_code, safe="")
    params = _build_time_params(tr)
    ck = f"api:dc_san_health:{enc}:{_serialize_tr_cache_key(tr)}"

    def fetch() -> list[dict]:
        data = _get_json(_get_client_dc(), f"/api/v1/datacenters/{enc}/san/health", params=params)
        return data if isinstance(data, list) else []

    return _api_cache_get_with_stale(ck, fetch, [])


def get_dc_san_traffic_trend(dc_code: str, tr: Optional[dict]) -> list[dict]:
    enc = quote(dc_code, safe="")
    params = _build_time_params(tr)
    ck = f"api:dc_san_traffic_trend:{enc}:{_serialize_tr_cache_key(tr)}"

    def fetch() -> list[dict]:
        data = _get_json(_get_client_dc(), f"/api/v1/datacenters/{enc}/san/traffic-trend", params=params)
        return data if isinstance(data, list) else []

    return _api_cache_get_with_stale(ck, fetch, [])


def get_dc_san_bottleneck(dc_code: str, tr: Optional[dict]) -> dict:
    enc = quote(dc_code, safe="")
    params = _build_time_params(tr)
    ck = f"api:dc_san_bottleneck:{enc}:{_serialize_tr_cache_key(tr)}"

    def fetch() -> dict:
        data = _get_json(_get_client_dc(), f"/api/v1/datacenters/{enc}/san/bottleneck", params=params)
        return data if isinstance(data, dict) else {}

    return _api_cache_get_with_stale(ck, fetch, {})


def get_dc_storage_capacity(dc_code: str, tr: Optional[dict]) -> dict:
    enc = quote(dc_code, safe="")
    params = _build_time_params(tr)
    ck = f"api:dc_storage_cap:{enc}:{_serialize_tr_cache_key(tr)}"

    def fetch() -> dict:
        data = _get_json(_get_client_dc(), f"/api/v1/datacenters/{enc}/storage/capacity", params=params)
        return data if isinstance(data, dict) else {}

    return _api_cache_get_with_stale(ck, fetch, {})


def get_dc_datastore_mapping(dc_code: str, tr: Optional[dict]) -> dict:
    enc = quote(dc_code, safe="")
    params = _build_time_params(tr)
    ck = f"api:dc_datastore_mapping:{enc}:{_serialize_tr_cache_key(tr)}"

    def fetch() -> dict:
        data = _get_json(_get_client_dc(), f"/api/v1/datacenters/{enc}/storage/datastores", params=params)
        return data if isinstance(data, dict) else {}

    return _api_cache_get_with_stale(ck, fetch, {})


def get_dc_storage_performance(dc_code: str, tr: Optional[dict]) -> dict:
    enc = quote(dc_code, safe="")
    params = _build_time_params(tr)
    ck = f"api:dc_storage_perf:{enc}:{_serialize_tr_cache_key(tr)}"

    def fetch() -> dict:
        data = _get_json(_get_client_dc(), f"/api/v1/datacenters/{enc}/storage/performance", params=params)
        return data if isinstance(data, dict) else {}

    return _api_cache_get_with_stale(ck, fetch, {})


# ---------------------------------------------------------------------------
# Network Dashboard (Zabbix) + Intel Storage (Zabbix) - DC scoped
# ---------------------------------------------------------------------------


def _build_optional_params(base: dict[str, str], **kwargs: Optional[Any]) -> dict[str, str]:
    """Add non-None query params to base dict."""
    for k, v in kwargs.items():
        if v is not None:
            base[k] = str(v)
    return base


def get_dc_network_filters(
    dc_code: str,
    tr: Optional[dict],
    interface_scope: Optional[str] = None,
) -> dict:
    enc = quote(dc_code, safe="")
    params = _build_optional_params(_build_time_params(tr), interface_scope=interface_scope)
    scope_key = interface_scope or "overview"
    ck = f"api:dc_net_filters:{enc}:scope={scope_key}:{_serialize_tr_cache_key(tr)}"

    def fetch() -> dict:
        data = _get_json(_get_client_dc(), f"/api/v1/datacenters/{enc}/network/filters", params=params)
        return data if isinstance(data, dict) else {}

    return _api_cache_get_with_stale(ck, fetch, {})


def get_dc_network_port_summary(
    dc_code: str,
    tr: Optional[dict],
    manufacturer: Optional[str] = None,
    device_role: Optional[str] = None,
    device_name: Optional[str] = None,
    interface_scope: Optional[str] = None,
) -> dict:
    enc = quote(dc_code, safe="")
    params = _build_optional_params(
        _build_time_params(tr),
        manufacturer=manufacturer,
        device_role=device_role,
        device_name=device_name,
        interface_scope=interface_scope,
    )
    ck = f"api:dc_net_port_sum:{enc}:{json.dumps(sorted(params.items()), separators=(',', ':'), ensure_ascii=False)}"

    def fetch() -> dict:
        data = _get_json(
            _get_client_dc(),
            f"/api/v1/datacenters/{enc}/network/port-summary",
            params=params,
        )
        return data if isinstance(data, dict) else {}

    return _api_cache_get_with_stale(ck, fetch, {})


def get_dc_network_95th_percentile(
    dc_code: str,
    tr: Optional[dict],
    top_n: int = 20,
    manufacturer: Optional[str] = None,
    device_role: Optional[str] = None,
    device_name: Optional[str] = None,
    interface_scope: Optional[str] = None,
) -> dict:
    enc = quote(dc_code, safe="")
    params = _build_optional_params(
        _build_time_params(tr),
        top_n=top_n,
        manufacturer=manufacturer,
        device_role=device_role,
        device_name=device_name,
        interface_scope=interface_scope,
    )
    ck = f"api:dc_net_95:{enc}:{json.dumps(sorted(params.items()), separators=(',', ':'), ensure_ascii=False)}"

    def fetch() -> dict:
        data = _get_json(
            _get_client_dc(),
            f"/api/v1/datacenters/{enc}/network/95th-percentile",
            params=params,
        )
        return data if isinstance(data, dict) else {}

    return _api_cache_get_with_stale(ck, fetch, {})


def get_dc_network_interface_table(
    dc_code: str,
    tr: Optional[dict],
    page: int = 1,
    page_size: int = 50,
    search: Optional[str] = None,
    manufacturer: Optional[str] = None,
    device_role: Optional[str] = None,
    device_name: Optional[str] = None,
    interface_scope: Optional[str] = None,
) -> dict:
    enc = quote(dc_code, safe="")
    params = _build_optional_params(
        _build_time_params(tr),
        page=page,
        page_size=page_size,
        search=search or "",
        manufacturer=manufacturer,
        device_role=device_role,
        device_name=device_name,
        interface_scope=interface_scope,
    )
    ck = f"api:dc_net_iface:{enc}:{json.dumps(sorted(params.items()), separators=(',', ':'), ensure_ascii=False)}"

    def fetch() -> dict:
        data = _get_json(
            _get_client_dc(),
            f"/api/v1/datacenters/{enc}/network/interface-table",
            params=params,
        )
        return data if isinstance(data, dict) else {}
    return _api_cache_get_with_stale(ck, fetch, {})


def get_dc_network_interface_export(
    dc_code: str,
    tr: Optional[dict],
    search: Optional[str] = None,
    manufacturer: Optional[str] = None,
    device_role: Optional[str] = None,
    device_name: Optional[str] = None,
    interface_scope: Optional[str] = None,
) -> dict:
    enc = quote(dc_code, safe="")
    params = _build_optional_params(
        _build_time_params(tr),
        search=search or "",
        manufacturer=manufacturer,
        device_role=device_role,
        device_name=device_name,
        interface_scope=interface_scope,
    )
    ck = f"api:dc_net_iface_export:{enc}:{json.dumps(sorted(params.items()), separators=(',', ':'), ensure_ascii=False)}"

    def fetch() -> dict:
        data = _get_json(
            _get_client_dc(),
            f"/api/v1/datacenters/{enc}/network/interface-export",
            params=params,
        )
        return data if isinstance(data, dict) else {}

    return _api_cache_get_with_stale(ck, fetch, {})


def get_dc_network_firewall_summary(dc_code: str, tr: Optional[dict]) -> dict:
    enc = quote(dc_code, safe="")
    params = _build_time_params(tr)
    ck = f"api:dc_net_fw:{enc}:{_serialize_tr_cache_key(tr)}"

    def fetch() -> dict:
        data = _get_json(
            _get_client_dc(),
            f"/api/v1/datacenters/{enc}/network/firewall-summary",
            params=params,
        )
        return data if isinstance(data, dict) else {}

    return _api_cache_get_with_stale(ck, fetch, {})


def get_dc_network_load_balancer_summary(dc_code: str, tr: Optional[dict]) -> dict:
    enc = quote(dc_code, safe="")
    params = _build_time_params(tr)
    ck = f"api:dc_net_lb:{enc}:{_serialize_tr_cache_key(tr)}"

    def fetch() -> dict:
        data = _get_json(
            _get_client_dc(),
            f"/api/v1/datacenters/{enc}/network/load-balancer-summary",
            params=params,
        )
        return data if isinstance(data, dict) else {}

    return _api_cache_get_with_stale(ck, fetch, {})


def get_dc_zabbix_storage_capacity(dc_code: str, tr: Optional[dict], host: Optional[str] = None) -> dict:
    enc = quote(dc_code, safe="")
    params = _build_optional_params(_build_time_params(tr), host=host)
    ck = f"api:dc_zbx_cap:{enc}:{json.dumps(sorted(params.items()), separators=(',', ':'), ensure_ascii=False)}"

    def fetch() -> dict:
        data = _get_json(_get_client_dc(), f"/api/v1/datacenters/{enc}/zabbix-storage/capacity", params=params)
        return data if isinstance(data, dict) else {}

    return _api_cache_get_with_stale(ck, fetch, {})


def get_dc_zabbix_storage_trend(dc_code: str, tr: Optional[dict], host: Optional[str] = None) -> dict:
    enc = quote(dc_code, safe="")
    params = _build_optional_params(_build_time_params(tr), host=host)
    ck = f"api:dc_zbx_trend:{enc}:{json.dumps(sorted(params.items()), separators=(',', ':'), ensure_ascii=False)}"

    def fetch() -> dict:
        data = _get_json(_get_client_dc(), f"/api/v1/datacenters/{enc}/zabbix-storage/trend", params=params)
        return data if isinstance(data, dict) else {}

    return _api_cache_get_with_stale(ck, fetch, {})


def get_dc_zabbix_storage_devices(dc_code: str, tr: Optional[dict]) -> list[dict]:
    enc = quote(dc_code, safe="")
    params = _build_time_params(tr)
    ck = f"api:dc_zbx_devices:{enc}:{_serialize_tr_cache_key(tr)}"

    def fetch() -> list[dict]:
        data = _get_json(_get_client_dc(), f"/api/v1/datacenters/{enc}/zabbix-storage/devices", params=params)
        return data if isinstance(data, list) else []

    return _api_cache_get_with_stale(ck, fetch, [])


def get_dc_zabbix_disk_list(dc_code: str, tr: Optional[dict], host: Optional[str] = None) -> dict:
    if host is None:
        return {"items": []}
    enc = quote(dc_code, safe="")
    params = _build_optional_params(_build_time_params(tr), host=host)
    ck = f"api:dc_zbx_disk_list:{enc}:{json.dumps(sorted(params.items()), separators=(',', ':'), ensure_ascii=False)}"
    empty = {"items": []}

    def fetch() -> dict:
        data = _get_json(_get_client_dc(), f"/api/v1/datacenters/{enc}/zabbix-storage/disk-list", params=params)
        return data if isinstance(data, dict) else empty

    return _api_cache_get_with_stale(ck, fetch, empty)


def get_dc_zabbix_disk_trend(
    dc_code: str,
    tr: Optional[dict],
    host: Optional[str] = None,
    disk_name: Optional[str] = None,
) -> dict:
    if host is None or disk_name is None:
        return {"series": []}
    enc = quote(dc_code, safe="")
    params = _build_optional_params(_build_time_params(tr), host=host, disk=disk_name)
    ck = f"api:dc_zbx_disk_trend:{enc}:{json.dumps(sorted(params.items()), separators=(',', ':'), ensure_ascii=False)}"
    empty = {"series": []}

    def fetch() -> dict:
        data = _get_json(_get_client_dc(), f"/api/v1/datacenters/{enc}/zabbix-storage/disk-trend", params=params)
        return data if isinstance(data, dict) else empty

    return _api_cache_get_with_stale(ck, fetch, empty)


def get_dc_zabbix_disk_health(dc_code: str, tr: Optional[dict]) -> dict:
    enc = quote(dc_code, safe="")
    params = _build_time_params(tr)
    ck = f"api:dc_zbx_disk_health:{enc}:{_serialize_tr_cache_key(tr)}"

    def fetch() -> dict:
        data = _get_json(_get_client_dc(), f"/api/v1/datacenters/{enc}/zabbix-storage/disk-health", params=params)
        return data if isinstance(data, dict) else {}

    return _api_cache_get_with_stale(ck, fetch, {})


def get_dc_racks(dc_code: str) -> dict:
    enc = quote(dc_code, safe="")
    empty = {"racks": [], "summary": {}}
    ck = f"api:dc_racks:{enc}"

    def fetch() -> dict:
        data = _get_json(_get_client_dc(), f"/api/v1/datacenters/{enc}/racks")
        return data if isinstance(data, dict) else empty

    return _api_cache_get_with_stale(ck, fetch, empty)


def get_rack_devices(dc_code: str, rack_name: str) -> dict:
    enc_dc = quote(dc_code, safe="")
    enc_rack = quote(rack_name, safe="")
    empty = {"devices": []}
    ck = f"api:rack_devices:{enc_dc}:{enc_rack}"

    def fetch() -> dict:
        data = _get_json(_get_client_dc(), f"/api/v1/datacenters/{enc_dc}/racks/{enc_rack}/devices")
        return data if isinstance(data, dict) else empty

    return _api_cache_get_with_stale(ck, fetch, empty)


def _auranotify_start_date(tr: Optional[dict]) -> str:
    from src.utils.time_range import time_range_to_bounds

    start_ts, _ = time_range_to_bounds(tr)
    return start_ts.strftime("%Y-%m-%dT%H:%M:%S")


def _auranotify_end_date_iso(tr: Optional[dict]) -> str:
    from src.utils.time_range import time_range_to_bounds

    _, end_ts = time_range_to_bounds(tr)
    return end_ts.strftime("%Y-%m-%dT%H:%M:%S")


# TTL cache for customer availability (AuraNotify), stored in the shared
# cache_service backend so all pods share it. Scheduler force-refreshes on
# interval. The local lock only serializes the read/refresh within one process.
_CUSTOMER_AVAIL_LOCK = threading.Lock()
CUSTOMER_AVAIL_TTL_SECONDS = 900


def _customer_availability_cache_key(customer_name: str, tr: Optional[dict]) -> str:
    from src.utils.time_range import default_time_range

    t = tr if tr is not None else default_time_range()
    return f"api:cust_avail:{customer_name or ''}:{t.get('start', '')}:{t.get('end', '')}"


def _fetch_customer_availability_bundle_uncached(customer_name: str, tr: Optional[dict]) -> dict[str, Any]:
    from src.services import auranotify_client as aura

    return aura.get_customer_availability_bundle(customer_name or "", _auranotify_start_date(tr))


def clear_customer_availability_bundle_cache() -> None:
    """Clear customer availability cache (tests / admin)."""
    with _CUSTOMER_AVAIL_LOCK:
        _api_response_cache.delete_prefix("api:cust_avail:")


def get_customer_availability_bundle(
    customer_name: str,
    tr: Optional[dict],
    *,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """
    AuraNotify: service + VM downtimes and per-VM outage counts for the selected customer.

    Results are cached in memory for CUSTOMER_AVAIL_TTL_SECONDS (default 15 minutes) so repeated
    page renders do not hit AuraNotify on every request. Pass force_refresh=True for scheduler jobs.
    On fetch failure, the last successful payload is retained (never replaced by an empty error body).
    """
    key = _customer_availability_cache_key(customer_name, tr)
    now = time.time()
    _empty_bundle = {
        "service_downtimes": [],
        "vm_downtimes": [],
        "vm_outage_counts": {},
        "customer_id": None,
        "customer_ids": [],
    }
    with _CUSTOMER_AVAIL_LOCK:
        prev = _api_response_cache.get(key)
        if not force_refresh and prev is not None and (now - prev[0]) < CUSTOMER_AVAIL_TTL_SECONDS:
            return deepcopy(prev[1])
        try:
            data = _fetch_customer_availability_bundle_uncached(customer_name, tr)
        except Exception:
            if prev is not None:
                return deepcopy(prev[1])
            data = _empty_bundle
        _api_response_cache.set(key, (now, data))
        return deepcopy(data)


def get_dc_availability_sla_item(dc_code: str, dc_display_name: str, tr: Optional[dict]) -> Optional[dict[str, Any]]:
    """AuraNotify: one datacenter-services item matched to this DC (by name or code)."""
    ck = f"api:dc_avail_sla_item:{quote(dc_code or '', safe='')}:{quote(dc_display_name or '', safe='')}:{_serialize_tr_cache_key(tr)}"
    try:
        from src.services import auranotify_client as aura

        items = aura.get_dc_services_availability(
            _auranotify_start_date(tr),
            _auranotify_end_date_iso(tr),
        )
        out: Optional[dict[str, Any]] = None
        for hint in (dc_display_name or "", dc_code or ""):
            it = aura.match_dc_group_item(items, hint)
            if it:
                out = it
                break
        if out is not None:
            _api_response_cache.set(ck, out)
        return deepcopy(out) if out is not None else None
    except Exception:
        hit = _api_response_cache.get(ck)
        return deepcopy(hit) if isinstance(hit, dict) else None


class DcAvailabilitySlaBatchResult(TypedDict):
    status: Literal["ok", "empty", "error"]
    items_map: dict[str, Optional[dict[str, Any]]]
    raw_count: int


def get_dc_availability_sla_items_for_dcs(
    dc_rows: list[dict[str, Any]],
    tr: Optional[dict],
    *,
    force_refresh: bool = False,
) -> DcAvailabilitySlaBatchResult:
    """
    Fetch datacenter-services SLA items via datacenter-api and match each DC row by id.

    Returns status plus map ``dc_id`` (str) -> matched SLA item or None.
    On transport errors, reuses the last successful cached items list when available.
    """
    import re
    from src.utils.dc_display import format_dc_display_name

    empty_result: DcAvailabilitySlaBatchResult = {
        "status": "empty",
        "items_map": {},
        "raw_count": 0,
    }
    if not dc_rows:
        return empty_result

    ck = f"api:dc_svc_sla_items:{_serialize_tr_cache_key(tr)}"

    def fetch() -> list:
        data = _get_json(_get_client_dc(), "/api/v1/sla/datacenter-services", params=_build_time_params(tr))
        if isinstance(data, dict):
            return data.get("items") or []
        return []

    status: Literal["ok", "empty", "error"] = "ok"
    items: list = []
    prev_cached = _api_response_cache.get(ck)
    try:
        if force_refresh:
            _api_response_cache.delete(ck)
        stale = _api_response_cache.get(ck)
        if stale is not None and isinstance(stale, list) and not force_refresh:
            items = stale
        else:
            items = fetch()
            if items:
                _api_response_cache.set(ck, items)
        if not items:
            status = "empty"
    except _HTTP_ERRORS as exc:
        logger.warning("get_dc_availability_sla_items_for_dcs fetch failed: %s", exc)
        hit = _api_response_cache.get(ck)
        if hit is None and isinstance(prev_cached, list):
            hit = prev_cached
        if hit is not None and isinstance(hit, list) and hit:
            items = hit
            status = "ok"
        else:
            status = "error"
    except Exception as exc:
        logger.warning("get_dc_availability_sla_items_for_dcs unexpected error: %s", exc)
        hit = _api_response_cache.get(ck)
        if hit is None and isinstance(prev_cached, list):
            hit = prev_cached
        if hit is not None and isinstance(hit, list) and hit:
            items = hit
            status = "ok"
        else:
            status = "error"

    _dc_code_re = re.compile(r"\b(dc\d+|ict\d+|az\d+|uz\d+)\b", re.IGNORECASE)

    def _match(hint: str) -> Optional[dict[str, Any]]:
        hint_l = (hint or "").strip().lower()
        if not hint_l:
            return None
        for it in items:
            gn = str(it.get("group_name") or "").strip().lower()
            if gn == hint_l:
                return it
        for it in items:
            gn = str(it.get("group_name") or "").strip().lower()
            if hint_l in gn or gn in hint_l:
                return it
        for tok in _dc_code_re.findall(hint_l):
            pat = re.compile(r"\b" + re.escape(tok) + r"\b", re.IGNORECASE)
            for it in items:
                if pat.search(str(it.get("group_name") or "")):
                    return it
        return None

    out: dict[str, Optional[dict[str, Any]]] = {}
    for row in dc_rows:
        rid = row.get("id")
        if rid is None:
            continue
        sid = str(rid)
        dc_name = format_dc_display_name(row.get("name"), row.get("description")) or str(row.get("name") or sid)
        matched: Optional[dict[str, Any]] = None
        for hint in (dc_name, sid):
            m = _match(hint)
            if m:
                matched = m
                break
        out[sid] = deepcopy(matched) if matched is not None else None

    return {
        "status": status,
        "items_map": out,
        "raw_count": len(items),
    }


# ---------------------------------------------------------------------------
# CRM Sales API functions
# ---------------------------------------------------------------------------

# CRM sales cache lives in the shared cache_service backend (keys api:crm_sales_*)
# so all pods share it, instead of a private per-process dict.
CRM_SALES_CACHE_TTL_SECONDS = 900
CRM_SALES_CACHE_VERSION = "prod-v1"


def _crm_sales_cache_get(
    cache_key: str,
    fetch_normalized: Callable[[], Any],
    empty_fallback: Any,
) -> Any:
    now = time.time()
    prev = _api_response_cache.get(cache_key)
    if prev is not None and (now - prev[0]) < CRM_SALES_CACHE_TTL_SECONDS:
        return _clone(prev[1])
    try:
        out = fetch_normalized()
        if _should_persist_api_cache(out, empty_fallback):
            _api_response_cache.set(cache_key, (now, out))
        return out
    except _HTTP_ERRORS:
        if prev is not None:
            return _clone(prev[1])
        return _clone(empty_fallback)


def get_customer_sales_summary(name: str) -> dict:
    enc = quote(name, safe="")
    ck = f"api:crm_sales_summary:{CRM_SALES_CACHE_VERSION}:{enc}"

    def fetch() -> dict:
        data = _get_json(_get_client_cust(), f"/api/v1/customers/{enc}/sales/summary")
        return data if isinstance(data, dict) else {}

    return _crm_sales_cache_get(ck, fetch, {})


def get_customer_sales_items(name: str) -> list:
    enc = quote(name, safe="")

    def fetch() -> list:
        data = _get_json(_get_client_cust(), f"/api/v1/customers/{enc}/sales/items")
        return data if isinstance(data, list) else []

    ck = f"api:crm_sales_items:{CRM_SALES_CACHE_VERSION}:{enc}"
    return _crm_sales_cache_get(ck, fetch, [])


def get_customer_sales_active_orders(name: str) -> list:
    enc = quote(name, safe="")

    def fetch() -> list:
        data = _get_json(_get_client_cust(), f"/api/v1/customers/{enc}/sales/active-orders")
        return data if isinstance(data, list) else []

    ck = f"api:crm_sales_active_orders:{CRM_SALES_CACHE_VERSION}:{enc}"
    return _crm_sales_cache_get(ck, fetch, [])


def get_customer_sales_active_items(name: str) -> list:
    enc = quote(name, safe="")

    def fetch() -> list:
        data = _get_json(_get_client_cust(), f"/api/v1/customers/{enc}/sales/active-items")
        return data if isinstance(data, list) else []

    ck = f"api:crm_sales_active_items:{CRM_SALES_CACHE_VERSION}:{enc}"
    return _crm_sales_cache_get(ck, fetch, [])


def get_customer_sales_service_breakdown(name: str) -> list:
    enc = quote(name, safe="")

    def fetch() -> list:
        data = _get_json(_get_client_cust(), f"/api/v1/customers/{enc}/sales/service-breakdown")
        return data if isinstance(data, list) else []

    ck = f"api:crm_sales_service_breakdown:{CRM_SALES_CACHE_VERSION}:{enc}"
    return _crm_sales_cache_get(ck, fetch, [])


def get_customer_sales_efficiency(name: str) -> list:
    enc = quote(name, safe="")

    def fetch() -> list:
        data = _get_json(_get_client_cust(), f"/api/v1/customers/{enc}/sales/efficiency")
        return data if isinstance(data, list) else []

    ck = f"api:crm_sales_efficiency:{CRM_SALES_CACHE_VERSION}:{enc}"
    return _crm_sales_cache_get(ck, fetch, [])


def get_customer_catalog_valuation(name: str) -> list:
    enc = quote(name, safe="")

    def fetch() -> list:
        data = _get_json(_get_client_cust(), f"/api/v1/customers/{enc}/sales/catalog-valuation")
        return data if isinstance(data, list) else []

    ck = f"api:crm_catalog_valuation:{CRM_SALES_CACHE_VERSION}:{enc}"
    return _crm_sales_cache_get(ck, fetch, [])


def get_dc_sales_potential(dc_code: str) -> dict:
    enc = quote(dc_code, safe="")

    def fetch() -> dict:
        data = _get_json(_get_client_dc(), f"/api/v1/datacenters/{enc}/sales-potential")
        return data if isinstance(data, dict) else {}

    ck = f"api:dc_sales_potential:{enc}"
    return _api_cache_get_with_stale(ck, fetch, {})


def get_dc_sales_potential_v2(dc_code: str) -> dict:
    enc = quote(dc_code, safe="")

    def fetch() -> dict:
        data = _get_json(_get_client_dc(), f"/api/v1/datacenters/{enc}/sales-potential/v2")
        return data if isinstance(data, dict) else {}

    ck = f"api:dc_sales_potential_v2:{enc}"
    return _api_cache_get_with_stale(ck, fetch, {})


def get_customer_efficiency_by_category(name: str, tr: Optional[dict] = None) -> list:
    enc = quote(name, safe="")

    def fetch() -> list:
        data = _get_json(
            _get_client_cust(),
            f"/api/v1/customers/{enc}/sales/efficiency-by-category",
            params=_build_time_params(tr),
        )
        return data if isinstance(data, list) else []

    ck = f"api:crm_efficiency_by_cat:{enc}:{_serialize_tr_cache_key(tr)}"
    return _api_cache_get_with_stale(ck, fetch, [])


def get_customer_resource_compliance(
    name: str,
    scope: str = "virtualization",
    tr: Optional[dict] = None,
) -> dict:
    enc = quote(name, safe="")
    scope_q = quote(scope, safe="")

    def fetch() -> dict:
        params = {**_build_time_params(tr), "scope": scope}
        data = _get_json(
            _get_client_cust(),
            f"/api/v1/customers/{enc}/sales/resource-compliance",
            params=params,
        )
        return data if isinstance(data, dict) else {}

    ck = f"api:crm_resource_compliance:{enc}:{scope_q}:{_serialize_tr_cache_key(tr)}"
    return _api_cache_get_with_stale(ck, fetch, {})


def get_crm_service_mapping_pages() -> list:
    def fetch() -> list:
        data = _get_json(_get_client_cust(), "/api/v1/crm/service-mapping/pages")
        return data if isinstance(data, list) else []

    return _api_cache_get_with_stale("api:crm_service_mapping_pages", fetch, [])


def get_crm_service_mappings() -> list:
    def fetch() -> list:
        data = _get_json(_get_client_cust(), "/api/v1/crm/service-mapping")
        return data if isinstance(data, list) else []

    return _api_cache_get_with_stale("api:crm_service_mappings", fetch, [])


def put_crm_service_mapping(
    productid: str,
    *,
    page_key: str,
    notes: Optional[str] = None,
) -> dict[str, Any]:
    enc = quote(productid, safe="")
    body: dict[str, Any] = {"page_key": page_key}
    if notes is not None:
        body["notes"] = notes
    out = _put_json(_get_client_cust(), f"/api/v1/crm/service-mapping/{enc}", body)
    _api_response_cache.delete("api:crm_service_mappings")
    return out if isinstance(out, dict) else {}


def delete_crm_service_mapping_override(productid: str) -> dict[str, Any]:
    enc = quote(productid, safe="")
    out = _delete_json(_get_client_cust(), f"/api/v1/crm/service-mapping/{enc}/override")
    _api_response_cache.delete("api:crm_service_mappings")
    return out if isinstance(out, dict) else {}


def get_crm_aliases() -> list:
    ck = "api:crm_aliases"

    def fetch() -> list:
        data = _get_json(_get_client_cust(), "/api/v1/crm/aliases")
        return data if isinstance(data, list) else []

    stale = _api_response_cache.get(ck)
    if stale is not None:
        if _SWR_TTL_SECONDS > 0:
            age = _swr_age(ck)
            if age is not None and age > _SWR_TTL_SECONDS:
                _schedule_swr_refresh(ck, fetch)
        return _clone(stale)

    with _inflight_lock:
        ev = _inflight.get(ck)
        leader = ev is None
        if leader:
            ev = threading.Event()
            _inflight[ck] = ev
    if not leader:
        ev.wait(timeout=_INFLIGHT_WAIT_SECONDS)
        hit = _api_response_cache.get(ck)
        return _clone(hit) if hit is not None else []

    try:
        out = fetch()
        if _crm_aliases_response_cacheable(out):
            _api_response_cache.set(ck, out)
            _fetched_at[ck] = time.monotonic()
        return out
    except _HTTP_ERRORS as exc:
        logger.warning("CRM aliases fetch failed: %s", exc)
        hit = _api_response_cache.get(ck)
        if hit is not None:
            return _clone(hit)
        return []
    finally:
        with _inflight_lock:
            _inflight.pop(ck, None)
        ev.set()


def put_crm_alias(
    crm_accountid: str,
    *,
    canonical_customer_key: Optional[str] = None,
    netbox_musteri_value: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict[str, Any]:
    enc = quote(crm_accountid, safe="")
    body = {
        "canonical_customer_key": canonical_customer_key,
        "netbox_musteri_value": netbox_musteri_value,
        "notes": notes,
    }
    out = _put_json(_get_client_cust(), f"/api/v1/crm/aliases/{enc}", body)
    _api_response_cache.delete("api:crm_aliases")
    return out if isinstance(out, dict) else {}


def put_crm_source_mappings(
    crm_accountid: str,
    *,
    crm_account_name: Optional[str] = None,
    mappings: Optional[list[dict[str, Any]]] = None,
    notes: Optional[str] = None,
) -> list[dict[str, Any]]:
    enc = quote(crm_accountid, safe="")
    body = {
        "crm_account_name": crm_account_name,
        "mappings": mappings or [],
        "notes": notes,
    }
    out = _put_json(_get_client_cust(), f"/api/v1/crm/aliases/{enc}/source-mappings", body)
    _api_response_cache.delete("api:crm_aliases")
    return out if isinstance(out, list) else []


def seed_boyner_source_mappings() -> dict[str, Any]:
    out = _post_json(_get_client_cust(), "/api/v1/crm/aliases/seed-boyner", {})
    _api_response_cache.delete("api:crm_aliases")
    return out if isinstance(out, dict) else {}


def delete_crm_alias(crm_accountid: str) -> dict[str, Any]:
    enc = quote(crm_accountid, safe="")
    out = _delete_json(_get_client_cust(), f"/api/v1/crm/aliases/{enc}")
    _api_response_cache.delete("api:crm_aliases")
    return out if isinstance(out, dict) else {}


def get_crm_discovery_counts() -> list:
    def fetch() -> list:
        data = _get_json(_get_client_crm(), "/api/v1/crm/config/discovery-counts")
        return data if isinstance(data, list) else []

    return _api_cache_get_with_stale("api:crm_discovery_counts", fetch, [])


def get_crm_config_thresholds() -> list:
    def fetch() -> list:
        data = _get_json(_get_client_crm(), "/api/v1/crm/config/thresholds")
        return data if isinstance(data, list) else []

    return _api_cache_get_with_stale("api:crm_config_thresholds", fetch, [])


def put_crm_config_threshold(
    *,
    resource_type: str,
    dc_code: str,
    sellable_limit_pct: float,
    notes: Optional[str] = None,
    panel_key: Optional[str] = None,
) -> dict[str, Any]:
    body = {
        "resource_type": resource_type,
        "dc_code": dc_code,
        "sellable_limit_pct": sellable_limit_pct,
        "notes": notes,
        "panel_key": panel_key or None,
    }
    out = _put_json(_get_client_crm(), "/api/v1/crm/config/thresholds", body)
    _api_response_cache.delete("api:crm_config_thresholds")
    _invalidate_sellable_caches()
    return out if isinstance(out, dict) else {}


def delete_crm_config_threshold(threshold_id: int) -> dict[str, Any]:
    out = _delete_json(_get_client_crm(), f"/api/v1/crm/config/thresholds/{threshold_id}")
    _api_response_cache.delete("api:crm_config_thresholds")
    _invalidate_sellable_caches()
    return out if isinstance(out, dict) else {}


def get_crm_price_overrides() -> list:
    def fetch() -> list:
        data = _get_json(_get_client_crm(), "/api/v1/crm/config/price-overrides")
        return data if isinstance(data, list) else []

    return _api_cache_get_with_stale("api:crm_price_overrides", fetch, [])


def put_crm_price_override(
    productid: str,
    *,
    product_name: Optional[str],
    unit_price_tl: float,
    resource_unit: Optional[str] = None,
    currency: Optional[str] = "TL",
    notes: Optional[str] = None,
) -> dict[str, Any]:
    enc = quote(productid, safe="")
    body: dict[str, Any] = {
        "product_name": product_name,
        "unit_price_tl": unit_price_tl,
        "resource_unit": resource_unit,
        "currency": currency,
        "notes": notes,
    }
    out = _put_json(_get_client_crm(), f"/api/v1/crm/config/price-overrides/{enc}", body)
    _api_response_cache.delete("api:crm_price_overrides")
    _invalidate_sellable_caches()
    return out if isinstance(out, dict) else {}


def delete_crm_price_override(productid: str) -> dict[str, Any]:
    enc = quote(productid, safe="")
    out = _delete_json(_get_client_crm(), f"/api/v1/crm/config/price-overrides/{enc}")
    _api_response_cache.delete("api:crm_price_overrides")
    _invalidate_sellable_caches()
    return out if isinstance(out, dict) else {}


def get_crm_calc_config() -> list:
    def fetch() -> list:
        data = _get_json(_get_client_crm(), "/api/v1/crm/config/variables")
        return data if isinstance(data, list) else []

    return _api_cache_get_with_stale("api:crm_calc_config", fetch, [])


# ---------------------------------------------------------------------------
# NetBox / Loki visualization exclusions
# ---------------------------------------------------------------------------


def get_netbox_device_roles() -> list[dict[str, Any]]:
    def fetch() -> list[dict[str, Any]]:
        data = _get_json(_get_client_dc(), "/api/v1/netbox/device-roles")
        return data if isinstance(data, list) else []

    return _api_cache_get_with_stale("api:netbox_device_roles", fetch, [])


def get_netbox_viz_exclusions() -> list[dict[str, Any]]:
    def fetch() -> list[dict[str, Any]]:
        data = _get_json(_get_client_cust(), "/api/v1/netbox/config/visualization-exclusions")
        return data if isinstance(data, list) else []

    return _api_cache_get_with_stale("api:netbox_viz_exclusions", fetch, [])


def put_netbox_viz_exclusion(
    *,
    view_scope: str,
    dimension_value: str,
    dimension: str = "device_role",
    notes: Optional[str] = None,
) -> dict[str, Any]:
    body = {
        "view_scope": view_scope,
        "dimension": dimension,
        "dimension_value": dimension_value,
        "notes": notes,
    }
    out = _put_json(_get_client_cust(), "/api/v1/netbox/config/visualization-exclusions", body)
    _invalidate_netbox_viz_caches()
    return out if isinstance(out, dict) else {}


def delete_netbox_viz_exclusion(exclusion_id: int) -> dict[str, Any]:
    out = _delete_json(
        _get_client_cust(),
        f"/api/v1/netbox/config/visualization-exclusions/{exclusion_id}",
    )
    _invalidate_netbox_viz_caches()
    return out if isinstance(out, dict) else {}


def _invalidate_netbox_viz_caches() -> None:
    """Clear GUI and datacenter-api caches affected by NetBox viz exclusions."""
    prefixes = (
        "api:phys_inv_",
        "api:dc_net_",
        "api:dc_storage_",
        "api:netbox_",
    )
    for prefix in prefixes:
        try:
            _api_response_cache.delete_prefix(prefix)
        except Exception:
            pass
    try:
        _post_json(_get_client_dc(), "/api/v1/admin/cache/invalidate-netbox-viz", {})
    except _HTTP_ERRORS:
        pass


# ---------------------------------------------------------------------------
# Sellable Potential dashboard endpoints (customer-api FAZ 5)
# ---------------------------------------------------------------------------


def get_sellable_summary(dc_code: str = "*", *, rollup_only: bool = False) -> dict:
    """Top-level dashboard payload (KPIs + family roll-up)."""
    def fetch() -> dict:
        qs = f"dc_code={quote(dc_code, safe='*')}"
        if rollup_only:
            qs += "&rollup_only=true"
        data = _get_json(_get_client_crm(), f"/api/v1/crm/sellable-potential/summary?{qs}")
        return data if isinstance(data, dict) else {}

    suffix = ":rollup" if rollup_only else ""
    cache_key = f"api:sellable_summary:{dc_code}{suffix}"
    return _api_cache_get_sellable_summary(cache_key, fetch, dc_code)


def get_sellable_summary_light(dc_code: str) -> dict:
    """Lightweight summary for DC View Summary tab (no nested panels[])."""
    return get_sellable_summary(dc_code, rollup_only=True)


def get_crm_inventory_overview(dc_code: str = "*", *, force_recompute: bool = False) -> dict:
    """Global CRM capacity vs entitled vs infra used overview."""
    def fetch() -> dict:
        params: list[tuple[str, str]] = [("dc_code", dc_code or "*")]
        if force_recompute:
            params.append(("force_recompute", "true"))
        qs = urlencode(params)
        with httpx.Client(
            base_url=CRM_ENGINE_URL,
            timeout=_INVENTORY_TIMEOUT,
            transport=_new_http_transport(),
        ) as client:
            data = _get_json(client, f"/api/v1/crm/inventory-overview?{qs}")
        return data if isinstance(data, dict) else {}

    if force_recompute:
        return fetch()

    cache_key = f"api:crm_inventory_overview:{dc_code}"
    return _api_cache_get_sellable_summary(cache_key, fetch, dc_code)


def _normalize_clusters_arg(clusters: Optional[list]) -> Optional[list[str]]:
    """Coerce a clusters argument into a clean list[str] or None.

    Accepts None / empty list / list with empties. Strips whitespace and drops
    empty strings; returns None when no usable cluster names remain.
    """
    if not clusters:
        return None
    cleaned: list[str] = []
    for c in clusters:
        if c is None:
            continue
        s = str(c).strip()
        if s:
            cleaned.append(s)
    return cleaned or None


def get_sellable_by_panel(
    dc_code: str = "*",
    family: Optional[str] = None,
    clusters: Optional[list[str]] = None,
) -> list:
    """Panel-level computation list. Optional family + cluster filter.

    When ``clusters`` is non-empty, crm-engine reads total + allocated for
    virt_classic / virt_hyperconverged panels from the datacenter-api
    /compute/{kind} endpoint so the values match the DC view Capacity Planning
    card for the same cluster selection.
    """
    qs = f"dc_code={quote(dc_code, safe='*')}"
    if family:
        qs += f"&family={quote(family, safe='')}"
    cl = _normalize_clusters_arg(clusters)
    if cl:
        qs += f"&clusters={quote(','.join(cl), safe=',')}"

    def fetch() -> list:
        data = _get_json(_get_client_crm(), f"/api/v1/crm/sellable-potential/by-panel?{qs}")
        return data if isinstance(data, list) else []

    cluster_key = ",".join(cl) if cl else "*"
    cache_key = f"api:sellable_by_panel:{dc_code}:{family or '*'}:{cluster_key}"
    return _api_cache_get_sellable_panels(cache_key, fetch, dc_code, family, cl)


def get_virt_sellable_panels(
    dc_code: str,
    classic_clusters: Optional[list[str]] = None,
    hyperconv_clusters: Optional[list[str]] = None,
) -> list:
    """All virt sellable panels in one CRM round-trip (classic + hyperconv + power)."""
    qs = f"dc_code={quote(dc_code, safe='*')}"
    cl_classic = _normalize_clusters_arg(classic_clusters)
    cl_hyper = _normalize_clusters_arg(hyperconv_clusters)
    if cl_classic:
        qs += f"&classic_clusters={quote(','.join(cl_classic), safe=',')}"
    if cl_hyper:
        qs += f"&hyperconv_clusters={quote(','.join(cl_hyper), safe=',')}"

    def fetch() -> list:
        data = _get_json(_get_client_crm(), f"/api/v1/crm/sellable-potential/virt-total?{qs}")
        return data if isinstance(data, list) else []

    cache_key = (
        f"api:virt_sellable_total:{dc_code}:"
        f"{','.join(cl_classic or [])}:{','.join(cl_hyper or [])}"
    )
    return _api_cache_get_sellable_panels(cache_key, fetch, dc_code, "virt_total", cl_classic)


def get_sellable_by_family(
    dc_code: str = "*",
    clusters: Optional[list[str]] = None,
) -> list:
    qs = f"dc_code={quote(dc_code, safe='*')}"
    cl = _normalize_clusters_arg(clusters)
    if cl:
        qs += f"&clusters={quote(','.join(cl), safe=',')}"

    def fetch() -> list:
        data = _get_json(_get_client_crm(), f"/api/v1/crm/sellable-potential/by-family?{qs}")
        return data if isinstance(data, list) else []

    cluster_key = ",".join(cl) if cl else "*"
    cache_key = f"api:sellable_by_family:{dc_code}:{cluster_key}"
    return _api_cache_get_with_stale(cache_key, fetch, [])


def get_metric_tags(prefix: Optional[str] = None, scope_type: str = "global", scope_id: str = "*") -> list:
    qs_parts = [f"scope_type={quote(scope_type, safe='')}", f"scope_id={quote(scope_id, safe='*')}"]
    if prefix:
        qs_parts.append(f"prefix={quote(prefix, safe='')}")

    def fetch() -> list:
        data = _get_json(_get_client_crm(), "/api/v1/crm/metric-tags?" + "&".join(qs_parts))
        return data if isinstance(data, list) else []

    cache_key = "api:metric_tags:" + ":".join(qs_parts)
    return _api_cache_get_with_stale(cache_key, fetch, [])


def get_metric_snapshots(metric_key: str, hours: int = 720, scope_id: str = "*") -> list:
    def fetch() -> list:
        url = (
            "/api/v1/crm/metric-tags/snapshots?"
            f"metric_key={quote(metric_key, safe='')}"
            f"&scope_id={quote(scope_id, safe='*')}"
            f"&hours={int(hours)}"
        )
        data = _get_json(_get_client_crm(), url)
        return data if isinstance(data, list) else []

    cache_key = f"api:metric_snapshots:{metric_key}:{scope_id}:{hours}"
    return _api_cache_get_with_stale(cache_key, fetch, [])


# ---------------------------------------------------------------------------
# Panel registry / infra source / ratios / unit conversions (Settings UI)
# ---------------------------------------------------------------------------


def get_panel_definitions() -> list:
    def fetch() -> list:
        data = _get_json(_get_client_crm(), "/api/v1/crm/panels")
        return data if isinstance(data, list) else []

    return _api_cache_get_with_stale("api:crm_panels", fetch, [])


def put_panel_definition(
    panel_key: str,
    *,
    label: str,
    family: str,
    resource_kind: str,
    display_unit: str = "GB",
    sort_order: int = 100,
    enabled: bool = True,
    notes: Optional[str] = None,
) -> dict[str, Any]:
    enc = quote(panel_key, safe="")
    body = {
        "label": label,
        "family": family,
        "resource_kind": resource_kind,
        "display_unit": display_unit,
        "sort_order": sort_order,
        "enabled": enabled,
        "notes": notes,
    }
    out = _put_json(_get_client_crm(), f"/api/v1/crm/panels/{enc}", body)
    _api_response_cache.delete("api:crm_panels")
    _invalidate_sellable_caches()
    return out if isinstance(out, dict) else {}


def get_panel_infra_source(panel_key: str, dc_code: str = "*") -> dict[str, Any]:
    enc = quote(panel_key, safe="")

    def fetch() -> dict[str, Any]:
        data = _get_json(_get_client_crm(), f"/api/v1/crm/panels/{enc}/infra-source?dc_code={quote(dc_code, safe='*')}")
        return data if isinstance(data, dict) else {}

    cache_key = f"api:crm_panel_infra_source:{panel_key}:{dc_code}"
    return _api_cache_get_with_stale(cache_key, fetch, {})


def put_panel_infra_source(
    panel_key: str,
    dc_code: str = "*",
    *,
    source_table: Optional[str] = None,
    total_column: Optional[str] = None,
    total_unit: Optional[str] = None,
    allocated_table: Optional[str] = None,
    allocated_column: Optional[str] = None,
    allocated_unit: Optional[str] = None,
    filter_clause: Optional[str] = None,
    manual_total: Optional[float] = None,
    manual_allocated: Optional[float] = None,
    notes: Optional[str] = None,
) -> dict[str, Any]:
    enc = quote(panel_key, safe="")
    body = {
        "dc_code": dc_code,
        "source_table": source_table,
        "total_column": total_column,
        "total_unit": total_unit,
        "allocated_table": allocated_table,
        "allocated_column": allocated_column,
        "allocated_unit": allocated_unit,
        "filter_clause": filter_clause,
        "manual_total": manual_total,
        "manual_allocated": manual_allocated,
        "notes": notes,
    }
    out = _put_json(_get_client_crm(), f"/api/v1/crm/panels/{enc}/infra-source", body)
    _api_response_cache.delete_prefix(f"api:crm_panel_infra_source:{panel_key}:")
    _api_response_cache.delete_prefix("api:sellable_snapshot_meta:")
    _invalidate_sellable_caches()
    return out if isinstance(out, dict) else {}


def get_resource_ratios() -> list:
    def fetch() -> list:
        data = _get_json(_get_client_crm(), "/api/v1/crm/resource-ratios")
        return data if isinstance(data, list) else []

    return _api_cache_get_with_stale("api:crm_resource_ratios", fetch, [])


def put_resource_ratio(
    family: str,
    *,
    dc_code: str = "*",
    cpu_per_unit: float = 1.0,
    ram_gb_per_unit: float = 8.0,
    storage_gb_per_unit: float = 100.0,
    notes: Optional[str] = None,
) -> dict[str, Any]:
    enc = quote(family, safe="")
    body = {
        "dc_code": dc_code,
        "cpu_per_unit": cpu_per_unit,
        "ram_gb_per_unit": ram_gb_per_unit,
        "storage_gb_per_unit": storage_gb_per_unit,
        "notes": notes,
    }
    out = _put_json(_get_client_crm(), f"/api/v1/crm/resource-ratios/{enc}", body)
    _api_response_cache.delete("api:crm_resource_ratios")
    _invalidate_sellable_caches()
    return out if isinstance(out, dict) else {}


def get_unit_conversions() -> list:
    def fetch() -> list:
        data = _get_json(_get_client_crm(), "/api/v1/crm/unit-conversions")
        return data if isinstance(data, list) else []

    return _api_cache_get_with_stale("api:crm_unit_conversions", fetch, [])


def put_unit_conversion(
    from_unit: str,
    to_unit: str,
    *,
    factor: float,
    operation: str = "divide",
    ceil_result: bool = False,
    notes: Optional[str] = None,
) -> dict[str, Any]:
    body = {
        "factor": factor,
        "operation": operation,
        "ceil_result": ceil_result,
        "notes": notes,
    }
    out = _put_json(
        _get_client_crm(),
        f"/api/v1/crm/unit-conversions/{quote(from_unit, safe='')}/{quote(to_unit, safe='')}",
        body,
    )
    _api_response_cache.delete("api:crm_unit_conversions")
    _invalidate_sellable_caches()
    return out if isinstance(out, dict) else {}


def delete_unit_conversion(from_unit: str, to_unit: str) -> dict[str, Any]:
    out = _delete_json(
        _get_client_crm(),
        f"/api/v1/crm/unit-conversions/{quote(from_unit, safe='')}/{quote(to_unit, safe='')}",
    )
    _api_response_cache.delete("api:crm_unit_conversions")
    _invalidate_sellable_caches()
    return out if isinstance(out, dict) else {}


def _invalidate_sellable_caches() -> None:
    """Drop all cached sellable computations after a config write.

    Called from PUT/DELETE endpoints that change panel definitions,
    infra source bindings, resource ratios or unit conversions.
    """
    _api_response_cache.delete_prefix("api:sellable_summary:")
    _api_response_cache.delete_prefix("api:sellable_by_panel:")
    _api_response_cache.delete_prefix("api:sellable_by_family:")
    _api_response_cache.delete_prefix("api:sellable_snapshot_meta:")
    _api_response_cache.delete_prefix("api:metric_tags:")
    _api_response_cache.delete_prefix("api:metric_snapshots:")


def put_crm_calc_config(
    config_key: str,
    *,
    config_value: str,
    value_type: Optional[str] = None,
    description: Optional[str] = None,
) -> dict[str, Any]:
    enc = quote(config_key, safe="")
    body: dict[str, Any] = {"config_value": config_value}
    if value_type is not None:
        body["value_type"] = value_type
    if description is not None:
        body["description"] = description
    out = _put_json(_get_client_crm(), f"/api/v1/crm/config/variables/{enc}", body)
    _api_response_cache.delete("api:crm_calc_config")
    return out if isinstance(out, dict) else {}


_ADMIN_CACHE_REFRESH_PATH = "/api/v1/admin/cache/refresh"


def _response_error_detail(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return (resp.text or "")[:800]


def refresh_platform_redis_caches() -> dict[str, Any]:
    """Flush Redis-backed caches on backend services and clear the GUI HTTP response cache.

    Calls datacenter-api, customer-api, and crm-engine ``POST /api/v1/admin/cache/refresh``.
    Uses an extended timeout because warming can take several minutes.
    """
    timeout = httpx.Timeout(600.0, connect=30.0)
    headers = _auth_headers()
    out: dict[str, Any] = {"services": {}, "gui_cache_cleared": False}
    targets: list[tuple[str, Callable[[], httpx.Client]]] = [
        ("datacenter_api", _get_client_dc),
        ("customer_api", _get_client_cust),
        ("crm_engine", _get_client_crm),
    ]
    for name, client_getter in targets:
        client = client_getter()
        try:
            r = client.post(_ADMIN_CACHE_REFRESH_PATH, headers=headers, timeout=timeout)
            r.raise_for_status()
            body = r.json() if r.content else {}
            out["services"][name] = {"ok": True, "data": body}
        except httpx.HTTPStatusError as exc:
            out["services"][name] = {
                "ok": False,
                "error": f"HTTP {exc.response.status_code}",
                "detail": _response_error_detail(exc.response),
            }
        except _HTTP_ERRORS as exc:
            out["services"][name] = {"ok": False, "error": str(exc)}
        except Exception as exc:
            out["services"][name] = {"ok": False, "error": str(exc)}
    try:
        # cache_service.clear() flushes the whole shared cache, which now
        # includes the customer-availability and CRM-sales entries too.
        _api_response_cache.clear()
        out["gui_cache_cleared"] = True
    except Exception as exc:
        out["gui_cache_error"] = str(exc)
    return out


_EMPTY_HMDL_TOPOLOGY: dict[str, Any] = {
    "hub_dc": "DC13",
    "source_node": {"id": "LOKI", "label": "Loki Inventory", "role": "source"},
    "generated_at": None,
    "last_prod_run_id": None,
    "last_prod_run_at": None,
    "nodes": [],
    "edges": [],
    "synced_dc_count": 0,
    "total_dc_count": 0,
    "configured_location_count": 0,
    "no_configured_proxy_count": 0,
    "connected_environment_count": 0,
    "connectivity_issue_environment_count": 0,
    "dc_statuses": {},
}

_EMPTY_HMDL_SUMMARY: dict[str, Any] = {
    "generated_at": None,
    "last_prod_run_id": None,
    "last_prod_run_at": None,
    "synced_dc_count": 0,
    "total_dc_count": 0,
    "configured_location_count": 0,
    "no_configured_proxy_count": 0,
    "connected_environment_count": 0,
    "connectivity_issue_environment_count": 0,
    "synced_proxy_count": 0,
    "total_proxy_count": 0,
    "dc_statuses": {},
}


def get_hmdl_topology() -> dict[str, Any]:
    try:
        data = _get_json(_get_client_hmdl(), "/api/v1/collectors/topology")
        return data if isinstance(data, dict) else _clone(_EMPTY_HMDL_TOPOLOGY)
    except _HTTP_ERRORS as exc:
        logger.warning("hmdl-api topology unavailable: %s", exc)
        return _clone(_EMPTY_HMDL_TOPOLOGY)


def get_hmdl_sync_summary() -> dict[str, Any]:
    try:
        data = _get_json(_get_client_hmdl(), "/api/v1/collectors/sync-summary")
        return data if isinstance(data, dict) else _clone(_EMPTY_HMDL_SUMMARY)
    except _HTTP_ERRORS as exc:
        logger.warning("hmdl-api sync-summary unavailable: %s", exc)
        return _clone(_EMPTY_HMDL_SUMMARY)


def get_hmdl_dc_summary(dc_code: str) -> dict[str, Any]:
    enc = quote((dc_code or "").strip().upper(), safe="")
    try:
        data = _get_json(_get_client_hmdl(), f"/api/v1/collectors/dc/{enc}")
        return data if isinstance(data, dict) else {}
    except _HTTP_ERRORS as exc:
        logger.warning("hmdl-api dc summary unavailable dc=%s: %s", dc_code, exc)
        return {}


def get_hmdl_dc_targets(
    dc_code: str,
    *,
    category: str | None = None,
    entity_name: str | None = None,
    ip: str | None = None,
) -> dict[str, Any]:
    enc = quote((dc_code or "").strip().upper(), safe="")
    params: dict[str, str] = {}
    if category:
        params["category"] = category
    if entity_name:
        params["entity_name"] = entity_name
    if ip:
        params["ip"] = ip
    try:
        data = _get_json(_get_client_hmdl(), f"/api/v1/collectors/dc/{enc}/targets", params=params or None)
        return data if isinstance(data, dict) else {"items": []}
    except _HTTP_ERRORS as exc:
        logger.warning("hmdl-api dc targets unavailable dc=%s: %s", dc_code, exc)
        return {"items": []}


def get_hmdl_locations() -> dict[str, Any]:
    try:
        data = _get_json(_get_client_hmdl(), "/api/v1/collectors/locations")
        return data if isinstance(data, dict) else {"items": [], "total": 0}
    except _HTTP_ERRORS as exc:
        logger.warning("hmdl-api locations unavailable: %s", exc)
        return {"items": [], "total": 0}


_EMPTY_HMDL_COVERAGE: dict[str, Any] = {
    "summary": {"cluster": {}, "ibm_host": {"total": 0, "collected": 0, "missing": 0, "live": 0}},
    "clusters": [],
    "ibm_hosts": [],
    "locations": [],
    "dc_filter": None,
    "source_filter": None,
}


def get_hmdl_coverage(
    dc: str | None = None,
    *,
    source: str | None = None,
) -> dict[str, Any]:
    """Datalake coverage report: cluster/host present-absent + X/Y summary + reason."""
    params: dict[str, str] = {}
    if dc:
        params["dc"] = dc.strip().upper()
    if source:
        params["source"] = source.strip().lower()
    try:
        data = _get_json(_get_client_hmdl(), "/api/v1/collectors/coverage", params=params or None)
        return data if isinstance(data, dict) else _clone(_EMPTY_HMDL_COVERAGE)
    except _HTTP_ERRORS as exc:
        logger.warning("hmdl-api coverage unavailable: %s", exc)
        return _clone(_EMPTY_HMDL_COVERAGE)
