import json
import os
import threading
import time
from copy import deepcopy
from typing import Any, Callable, Optional
from urllib.parse import quote

import httpx

from src.services import cache_service as _api_response_cache

# Microservices: set per-service URLs, or use API_BASE_URL for a single gateway.
_API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
DATACENTER_API_URL = os.getenv("DATACENTER_API_URL", _API_BASE).rstrip("/")
CUSTOMER_API_URL = os.getenv("CUSTOMER_API_URL", _API_BASE).rstrip("/")
QUERY_API_URL = os.getenv("QUERY_API_URL", _API_BASE).rstrip("/")

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
_EMPTY_SLA_BY_DC: dict[str, dict] = {}

_transport = httpx.HTTPTransport(retries=3)
_client_dc = httpx.Client(base_url=DATACENTER_API_URL, timeout=30.0, transport=_transport)
_client_cust = httpx.Client(base_url=CUSTOMER_API_URL, timeout=30.0, transport=_transport)
_client_query = httpx.Client(base_url=QUERY_API_URL, timeout=30.0, transport=_transport)


def _clone(value: Any) -> Any:
    return deepcopy(value)


def _build_time_params(tr: Optional[dict]) -> dict[str, str]:
    if not tr:
        return {}
    preset = tr.get("preset")
    if preset in {"1h", "1d", "7d", "30d"}:
        return {"preset": preset}
    start = tr.get("start")
    end = tr.get("end")
    if start and end:
        return {"start": str(start), "end": str(end)}
    return {}


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


def _api_cache_get_with_stale(
    cache_key: str,
    fetch_normalized: Callable[[], Any],
    empty_fallback: Any,
) -> Any:
    """On success, persist normalized payload. On HTTP/transport errors, return last good payload if any."""
    try:
        out = fetch_normalized()
        _api_response_cache.set(cache_key, out)
        return out
    except _HTTP_ERRORS:
        hit = _api_response_cache.get(cache_key)
        if hit is not None:
            return _clone(hit)
        return _clone(empty_fallback)


def get_global_dashboard(tr: Optional[dict]) -> dict:
    ck = f"api:global_dashboard:{_serialize_tr_params(tr)}"

    def fetch() -> dict:
        data = _get_json(_client_dc, "/api/v1/dashboard/overview", params=_build_time_params(tr))
        return data if isinstance(data, dict) else _clone(_EMPTY_DASHBOARD)

    return _api_cache_get_with_stale(ck, fetch, _EMPTY_DASHBOARD)


def get_all_datacenters_summary(tr: Optional[dict]) -> list[dict]:
    ck = f"api:datacenters_summary:{_serialize_tr_params(tr)}"

    def fetch() -> list[dict]:
        data = _get_json(_client_dc, "/api/v1/datacenters/summary", params=_build_time_params(tr))
        return data if isinstance(data, list) else _clone(_EMPTY_DATACENTERS)

    return _api_cache_get_with_stale(ck, fetch, _EMPTY_DATACENTERS)


def get_dc_details(dc_id: str, tr: Optional[dict]) -> dict:
    enc = quote(dc_id, safe="")
    ck = f"api:dc_details:{enc}:{_serialize_tr_params(tr)}"

    def fetch() -> dict:
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}", params=_build_time_params(tr))
        return data if isinstance(data, dict) else _clone(_EMPTY_DC_DETAIL)

    return _api_cache_get_with_stale(ck, fetch, _EMPTY_DC_DETAIL)


def get_customer_list() -> list[str]:
    ck = "api:customer_list"

    def fetch() -> list[str]:
        data = _get_json(_client_cust, "/api/v1/customers")
        return data if isinstance(data, list) else _clone(_EMPTY_CUSTOMERS)

    return _api_cache_get_with_stale(ck, fetch, _EMPTY_CUSTOMERS)


def get_customer_resources(name: str, tr: Optional[dict]) -> dict:
    enc = quote(name, safe="")
    ck = f"api:customer_resources:{enc}:{_serialize_tr_params(tr)}"

    def fetch() -> dict:
        data = _get_json(
            _client_cust,
            f"/api/v1/customers/{enc}/resources",
            params=_build_time_params(tr),
        )
        return data if isinstance(data, dict) else _clone(_EMPTY_CUSTOMER)

    return _api_cache_get_with_stale(ck, fetch, _EMPTY_CUSTOMER)


def execute_registered_query(key: str, params: str) -> dict:
    enc_key = quote(key, safe="")
    ck = f"api:query:{enc_key}:{json.dumps(params or '', ensure_ascii=False)}"

    def fetch() -> dict:
        data = _get_json(_client_query, f"/api/v1/queries/{enc_key}", params={"params": params or ""})
        return data if isinstance(data, dict) else _clone(_EMPTY_QUERY)

    return _api_cache_get_with_stale(ck, fetch, _EMPTY_QUERY)


def get_sla_by_dc(tr: Optional[dict]) -> dict[str, dict]:
    """Return SLA entries keyed by DC code (uppercase)."""
    ck = f"api:sla_by_dc:{_serialize_tr_params(tr)}"

    def fetch() -> dict[str, dict]:
        data = _get_json(_client_dc, "/api/v1/sla", params=_build_time_params(tr))
        by_dc = (data or {}).get("by_dc") if isinstance(data, dict) else None
        return by_dc if isinstance(by_dc, dict) else _clone(_EMPTY_SLA_BY_DC)

    return _api_cache_get_with_stale(ck, fetch, _EMPTY_SLA_BY_DC)


def get_dc_s3_pools(dc_code: str, tr: Optional[dict]) -> dict:
    enc = quote(dc_code, safe="")
    empty = {"pools": [], "latest": {}, "growth": {}}
    ck = f"api:dc_s3_pools:{enc}:{_serialize_tr_params(tr)}"

    def fetch() -> dict:
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/s3/pools", params=_build_time_params(tr))
        return data if isinstance(data, dict) else empty

    return _api_cache_get_with_stale(ck, fetch, empty)


def get_customer_s3_vaults(customer_name: str, tr: Optional[dict]) -> dict:
    enc = quote(customer_name, safe="")
    empty = {"vaults": [], "latest": {}, "growth": {}}
    ck = f"api:customer_s3_vaults:{enc}:{_serialize_tr_params(tr)}"

    def fetch() -> dict:
        data = _get_json(_client_cust, f"/api/v1/customers/{enc}/s3/vaults", params=_build_time_params(tr))
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
    ck = f"api:customer_itsm_summary:{enc}:{_serialize_tr_params(tr)}"

    def fetch() -> dict:
        data = _get_json(_client_cust, f"/api/v1/customers/{enc}/itsm/summary", params=_build_time_params(tr))
        return data if isinstance(data, dict) else _EMPTY_ITSM_SUMMARY

    return _api_cache_get_with_stale(ck, fetch, _EMPTY_ITSM_SUMMARY)


def get_customer_itsm_extremes(customer_name: str, tr: Optional[dict]) -> dict:
    enc = quote(customer_name, safe="")
    ck = f"api:customer_itsm_extremes:{enc}:{_serialize_tr_params(tr)}"

    def fetch() -> dict:
        data = _get_json(_client_cust, f"/api/v1/customers/{enc}/itsm/extremes", params=_build_time_params(tr))
        return data if isinstance(data, dict) else _EMPTY_ITSM_EXTREMES

    return _api_cache_get_with_stale(ck, fetch, _EMPTY_ITSM_EXTREMES)


def get_customer_itsm_tickets(customer_name: str, tr: Optional[dict]) -> list:
    enc = quote(customer_name, safe="")
    ck = f"api:customer_itsm_tickets:{enc}:{_serialize_tr_params(tr)}"

    def fetch() -> list:
        data = _get_json(_client_cust, f"/api/v1/customers/{enc}/itsm/tickets", params=_build_time_params(tr))
        return data if isinstance(data, list) else []

    return _api_cache_get_with_stale(ck, fetch, [])


def get_dc_netbackup_pools(dc_code: str, tr: Optional[dict]) -> dict:
    enc = quote(dc_code, safe="")
    empty = {"pools": [], "rows": []}
    ck = f"api:dc_netbackup:{enc}:{_serialize_tr_params(tr)}"

    def fetch() -> dict:
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/backup/netbackup", params=_build_time_params(tr))
        return data if isinstance(data, dict) else empty

    return _api_cache_get_with_stale(ck, fetch, empty)


def get_dc_zerto_sites(dc_code: str, tr: Optional[dict]) -> dict:
    enc = quote(dc_code, safe="")
    empty = {"sites": [], "rows": []}
    ck = f"api:dc_zerto:{enc}:{_serialize_tr_params(tr)}"

    def fetch() -> dict:
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/backup/zerto", params=_build_time_params(tr))
        return data if isinstance(data, dict) else empty

    return _api_cache_get_with_stale(ck, fetch, empty)


def get_dc_veeam_repos(dc_code: str, tr: Optional[dict]) -> dict:
    enc = quote(dc_code, safe="")
    empty = {"repos": [], "rows": []}
    ck = f"api:dc_veeam:{enc}:{_serialize_tr_params(tr)}"

    def fetch() -> dict:
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/backup/veeam", params=_build_time_params(tr))
        return data if isinstance(data, dict) else empty

    return _api_cache_get_with_stale(ck, fetch, empty)


def get_classic_cluster_list(dc_code: str, tr: Optional[dict]) -> list[str]:
    enc = quote(dc_code, safe="")
    ck = f"api:classic_clusters:{enc}:{_serialize_tr_params(tr)}"

    def fetch() -> list[str]:
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/clusters/classic", params=_build_time_params(tr))
        return data if isinstance(data, list) else []

    return _api_cache_get_with_stale(ck, fetch, [])


def get_hyperconv_cluster_list(dc_code: str, tr: Optional[dict]) -> list[str]:
    enc = quote(dc_code, safe="")
    ck = f"api:hyperconv_clusters:{enc}:{_serialize_tr_params(tr)}"

    def fetch() -> list[str]:
        data = _get_json(
            _client_dc,
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
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/compute/classic", params=params)
        return data if isinstance(data, dict) else {}

    return _api_cache_get_with_stale(ck, fetch, {})


def get_hyperconv_metrics_filtered(
    dc_code: str, selected_clusters: Optional[list[str]], tr: Optional[dict]
) -> dict:
    enc = quote(dc_code, safe="")
    params = {**_build_time_params(tr), **_clusters_param(selected_clusters)}
    ck = f"api:hyperconv_metrics:{enc}:{json.dumps(sorted(params.items()), separators=(',', ':'))}"

    def fetch() -> dict:
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/compute/hyperconverged", params=params)
        return data if isinstance(data, dict) else {}

    return _api_cache_get_with_stale(ck, fetch, {})


def get_physical_inventory_dc(dc_name: str) -> dict:
    enc = quote(dc_name, safe="")
    empty = {"total": 0, "by_role": [], "by_role_manufacturer": []}
    ck = f"api:phys_inv_dc:{enc}"

    def fetch() -> dict:
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/physical-inventory")
        return data if isinstance(data, dict) else empty

    return _api_cache_get_with_stale(ck, fetch, empty)


def get_physical_inventory_overview_by_role() -> list[dict]:
    ck = "api:phys_inv_overview_by_role"

    def fetch() -> list[dict]:
        data = _get_json(_client_dc, "/api/v1/physical-inventory/overview/by-role")
        return data if isinstance(data, list) else []

    return _api_cache_get_with_stale(ck, fetch, [])


def get_physical_inventory_overview_manufacturer(role: str) -> list[dict]:
    enc = quote(role, safe="")
    ck = f"api:phys_inv_mfr:{enc}"

    def fetch() -> list[dict]:
        data = _get_json(_client_dc, "/api/v1/physical-inventory/overview/manufacturer", params={"role": enc})
        return data if isinstance(data, list) else []

    return _api_cache_get_with_stale(ck, fetch, [])


def get_physical_inventory_overview_location(role: str, manufacturer: str) -> list[dict]:
    ck = f"api:phys_inv_loc:{quote(role, safe='')}:{quote(manufacturer, safe='')}"

    def fetch() -> list[dict]:
        data = _get_json(
            _client_dc,
            "/api/v1/physical-inventory/overview/location",
            params={"role": role, "manufacturer": manufacturer},
        )
        return data if isinstance(data, list) else []

    return _api_cache_get_with_stale(ck, fetch, [])


def get_physical_inventory_customer() -> list[dict]:
    ck = "api:phys_inv_customer"

    def fetch() -> list[dict]:
        data = _get_json(_client_dc, "/api/v1/physical-inventory/customer")
        return data if isinstance(data, list) else []

    return _api_cache_get_with_stale(ck, fetch, [])


# ---------------------------------------------------------------------------
# Network > SAN (Brocade) + Power Mimari Storage (IBM)
# ---------------------------------------------------------------------------


def get_dc_san_switches(dc_code: str, tr: Optional[dict]) -> list[str]:
    enc = quote(dc_code, safe="")
    params = _build_time_params(tr)
    ck = f"api:dc_san_switches:{enc}:{_serialize_tr_params(tr)}"

    def fetch() -> list[str]:
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/san/switches", params=params)
        return data if isinstance(data, list) else []

    return _api_cache_get_with_stale(ck, fetch, [])


def get_dc_san_port_usage(dc_code: str, tr: Optional[dict]) -> dict:
    enc = quote(dc_code, safe="")
    params = _build_time_params(tr)
    ck = f"api:dc_san_port_usage:{enc}:{_serialize_tr_params(tr)}"

    def fetch() -> dict:
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/san/port-usage", params=params)
        return data if isinstance(data, dict) else {}

    return _api_cache_get_with_stale(ck, fetch, {})


def get_dc_san_health(dc_code: str, tr: Optional[dict]) -> list[dict]:
    enc = quote(dc_code, safe="")
    params = _build_time_params(tr)
    ck = f"api:dc_san_health:{enc}:{_serialize_tr_params(tr)}"

    def fetch() -> list[dict]:
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/san/health", params=params)
        return data if isinstance(data, list) else []

    return _api_cache_get_with_stale(ck, fetch, [])


def get_dc_san_traffic_trend(dc_code: str, tr: Optional[dict]) -> list[dict]:
    enc = quote(dc_code, safe="")
    params = _build_time_params(tr)
    ck = f"api:dc_san_traffic_trend:{enc}:{_serialize_tr_params(tr)}"

    def fetch() -> list[dict]:
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/san/traffic-trend", params=params)
        return data if isinstance(data, list) else []

    return _api_cache_get_with_stale(ck, fetch, [])


def get_dc_san_bottleneck(dc_code: str, tr: Optional[dict]) -> dict:
    enc = quote(dc_code, safe="")
    params = _build_time_params(tr)
    ck = f"api:dc_san_bottleneck:{enc}:{_serialize_tr_params(tr)}"

    def fetch() -> dict:
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/san/bottleneck", params=params)
        return data if isinstance(data, dict) else {}

    return _api_cache_get_with_stale(ck, fetch, {})


def get_dc_storage_capacity(dc_code: str, tr: Optional[dict]) -> dict:
    enc = quote(dc_code, safe="")
    params = _build_time_params(tr)
    ck = f"api:dc_storage_cap:{enc}:{_serialize_tr_params(tr)}"

    def fetch() -> dict:
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/storage/capacity", params=params)
        return data if isinstance(data, dict) else {}

    return _api_cache_get_with_stale(ck, fetch, {})


def get_dc_storage_performance(dc_code: str, tr: Optional[dict]) -> dict:
    enc = quote(dc_code, safe="")
    params = _build_time_params(tr)
    ck = f"api:dc_storage_perf:{enc}:{_serialize_tr_params(tr)}"

    def fetch() -> dict:
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/storage/performance", params=params)
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


def get_dc_network_filters(dc_code: str, tr: Optional[dict]) -> dict:
    enc = quote(dc_code, safe="")
    params = _build_time_params(tr)
    ck = f"api:dc_net_filters:{enc}:{_serialize_tr_params(tr)}"

    def fetch() -> dict:
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/network/filters", params=params)
        return data if isinstance(data, dict) else {}

    return _api_cache_get_with_stale(ck, fetch, {})


def get_dc_network_port_summary(
    dc_code: str,
    tr: Optional[dict],
    manufacturer: Optional[str] = None,
    device_role: Optional[str] = None,
    device_name: Optional[str] = None,
) -> dict:
    enc = quote(dc_code, safe="")
    params = _build_optional_params(
        _build_time_params(tr),
        manufacturer=manufacturer,
        device_role=device_role,
        device_name=device_name,
    )
    ck = f"api:dc_net_port_sum:{enc}:{json.dumps(sorted(params.items()), separators=(',', ':'), ensure_ascii=False)}"

    def fetch() -> dict:
        data = _get_json(
            _client_dc,
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
) -> dict:
    enc = quote(dc_code, safe="")
    params = _build_optional_params(
        _build_time_params(tr),
        top_n=top_n,
        manufacturer=manufacturer,
        device_role=device_role,
        device_name=device_name,
    )
    ck = f"api:dc_net_95:{enc}:{json.dumps(sorted(params.items()), separators=(',', ':'), ensure_ascii=False)}"

    def fetch() -> dict:
        data = _get_json(
            _client_dc,
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
    )
    ck = f"api:dc_net_iface:{enc}:{json.dumps(sorted(params.items()), separators=(',', ':'), ensure_ascii=False)}"

    def fetch() -> dict:
        data = _get_json(
            _client_dc,
            f"/api/v1/datacenters/{enc}/network/interface-table",
            params=params,
        )
        return data if isinstance(data, dict) else {}
    return _api_cache_get_with_stale(ck, fetch, {})


def get_dc_zabbix_storage_capacity(dc_code: str, tr: Optional[dict], host: Optional[str] = None) -> dict:
    enc = quote(dc_code, safe="")
    params = _build_optional_params(_build_time_params(tr), host=host)
    ck = f"api:dc_zbx_cap:{enc}:{json.dumps(sorted(params.items()), separators=(',', ':'), ensure_ascii=False)}"

    def fetch() -> dict:
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/zabbix-storage/capacity", params=params)
        return data if isinstance(data, dict) else {}

    return _api_cache_get_with_stale(ck, fetch, {})


def get_dc_zabbix_storage_trend(dc_code: str, tr: Optional[dict], host: Optional[str] = None) -> dict:
    enc = quote(dc_code, safe="")
    params = _build_optional_params(_build_time_params(tr), host=host)
    ck = f"api:dc_zbx_trend:{enc}:{json.dumps(sorted(params.items()), separators=(',', ':'), ensure_ascii=False)}"

    def fetch() -> dict:
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/zabbix-storage/trend", params=params)
        return data if isinstance(data, dict) else {}

    return _api_cache_get_with_stale(ck, fetch, {})


def get_dc_zabbix_storage_devices(dc_code: str, tr: Optional[dict]) -> list[dict]:
    enc = quote(dc_code, safe="")
    params = _build_time_params(tr)
    ck = f"api:dc_zbx_devices:{enc}:{_serialize_tr_params(tr)}"

    def fetch() -> list[dict]:
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/zabbix-storage/devices", params=params)
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
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/zabbix-storage/disk-list", params=params)
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
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/zabbix-storage/disk-trend", params=params)
        return data if isinstance(data, dict) else empty

    return _api_cache_get_with_stale(ck, fetch, empty)


def get_dc_zabbix_disk_health(dc_code: str, tr: Optional[dict]) -> dict:
    enc = quote(dc_code, safe="")
    params = _build_time_params(tr)
    ck = f"api:dc_zbx_disk_health:{enc}:{_serialize_tr_params(tr)}"

    def fetch() -> dict:
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/zabbix-storage/disk-health", params=params)
        return data if isinstance(data, dict) else {}

    return _api_cache_get_with_stale(ck, fetch, {})


def get_dc_racks(dc_code: str) -> dict:
    enc = quote(dc_code, safe="")
    empty = {"racks": [], "summary": {}}
    ck = f"api:dc_racks:{enc}"

    def fetch() -> dict:
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/racks")
        return data if isinstance(data, dict) else empty

    return _api_cache_get_with_stale(ck, fetch, empty)


def get_rack_devices(dc_code: str, rack_name: str) -> dict:
    enc_dc = quote(dc_code, safe="")
    enc_rack = quote(rack_name, safe="")
    empty = {"devices": []}
    ck = f"api:rack_devices:{enc_dc}:{enc_rack}"

    def fetch() -> dict:
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc_dc}/racks/{enc_rack}/devices")
        return data if isinstance(data, dict) else empty

    return _api_cache_get_with_stale(ck, fetch, empty)


def _auranotify_start_date(tr: Optional[dict]) -> str:
    from src.utils.time_range import time_range_to_bounds

    start_ts, _ = time_range_to_bounds(tr)
    return start_ts.strftime("%Y-%m-%dT%H:%M:%S")


# In-memory TTL cache for customer availability (AuraNotify). Scheduler force-refreshes on interval.
_CUSTOMER_AVAIL_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CUSTOMER_AVAIL_LOCK = threading.Lock()
CUSTOMER_AVAIL_TTL_SECONDS = 900


def _customer_availability_cache_key(customer_name: str, tr: Optional[dict]) -> str:
    from src.utils.time_range import default_time_range

    t = tr if tr is not None else default_time_range()
    return f"{customer_name or ''}:{t.get('start', '')}:{t.get('end', '')}"


def _fetch_customer_availability_bundle_uncached(customer_name: str, tr: Optional[dict]) -> dict[str, Any]:
    from src.services import auranotify_client as aura

    return aura.get_customer_availability_bundle(customer_name or "", _auranotify_start_date(tr))


def clear_customer_availability_bundle_cache() -> None:
    """Clear in-memory customer availability cache (tests / admin)."""
    with _CUSTOMER_AVAIL_LOCK:
        _CUSTOMER_AVAIL_CACHE.clear()


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
        prev = _CUSTOMER_AVAIL_CACHE.get(key)
        if not force_refresh and prev is not None and (now - prev[0]) < CUSTOMER_AVAIL_TTL_SECONDS:
            return deepcopy(prev[1])
        try:
            data = _fetch_customer_availability_bundle_uncached(customer_name, tr)
        except Exception:
            if prev is not None:
                return deepcopy(prev[1])
            data = _empty_bundle
        _CUSTOMER_AVAIL_CACHE[key] = (now, data)
        return deepcopy(data)


def get_dc_availability_sla_item(dc_code: str, dc_display_name: str, tr: Optional[dict]) -> Optional[dict[str, Any]]:
    """AuraNotify: one datacenter-services item matched to this DC (by name or code)."""
    ck = f"api:dc_avail_sla_item:{quote(dc_code or '', safe='')}:{quote(dc_display_name or '', safe='')}:{_serialize_tr_params(tr)}"
    try:
        from src.services import auranotify_client as aura

        items = aura.get_dc_services_availability(_auranotify_start_date(tr))
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
