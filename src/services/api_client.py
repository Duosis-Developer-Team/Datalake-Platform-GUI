import os
from copy import deepcopy
from typing import Any, Optional
from urllib.parse import quote

import httpx

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
    "meta": {"name": "", "location": ""},
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
    if preset in {"1d", "7d", "30d"}:
        return {"preset": preset}
    start = tr.get("start")
    end = tr.get("end")
    if start and end:
        return {"start": str(start), "end": str(end)}
    return {}


def _get_json(client: httpx.Client, path: str, params: Optional[dict[str, str]] = None) -> Any:
    response = client.get(path, params=params)
    response.raise_for_status()
    return response.json()


def get_global_dashboard(tr: Optional[dict]) -> dict:
    try:
        data = _get_json(_client_dc, "/api/v1/dashboard/overview", params=_build_time_params(tr))
        return data if isinstance(data, dict) else _clone(_EMPTY_DASHBOARD)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return _clone(_EMPTY_DASHBOARD)


def get_all_datacenters_summary(tr: Optional[dict]) -> list[dict]:
    try:
        data = _get_json(_client_dc, "/api/v1/datacenters/summary", params=_build_time_params(tr))
        return data if isinstance(data, list) else _clone(_EMPTY_DATACENTERS)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return _clone(_EMPTY_DATACENTERS)


def get_dc_details(dc_id: str, tr: Optional[dict]) -> dict:
    try:
        encoded_dc_id = quote(dc_id, safe="")
        data = _get_json(_client_dc, f"/api/v1/datacenters/{encoded_dc_id}", params=_build_time_params(tr))
        return data if isinstance(data, dict) else _clone(_EMPTY_DC_DETAIL)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return _clone(_EMPTY_DC_DETAIL)


def get_customer_list() -> list[str]:
    try:
        data = _get_json(_client_cust, "/api/v1/customers")
        return data if isinstance(data, list) else _clone(_EMPTY_CUSTOMERS)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return _clone(_EMPTY_CUSTOMERS)


def get_customer_resources(name: str, tr: Optional[dict]) -> dict:
    try:
        encoded_name = quote(name, safe="")
        data = _get_json(
            _client_cust,
            f"/api/v1/customers/{encoded_name}/resources",
            params=_build_time_params(tr),
        )
        return data if isinstance(data, dict) else _clone(_EMPTY_CUSTOMER)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return _clone(_EMPTY_CUSTOMER)


def execute_registered_query(key: str, params: str) -> dict:
    try:
        encoded_key = quote(key, safe="")
        data = _get_json(_client_query, f"/api/v1/queries/{encoded_key}", params={"params": params or ""})
        return data if isinstance(data, dict) else _clone(_EMPTY_QUERY)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return _clone(_EMPTY_QUERY)


def get_sla_by_dc(tr: Optional[dict]) -> dict[str, dict]:
    """Return SLA entries keyed by DC code (uppercase)."""
    try:
        data = _get_json(_client_dc, "/api/v1/sla", params=_build_time_params(tr))
        by_dc = (data or {}).get("by_dc") if isinstance(data, dict) else None
        return by_dc if isinstance(by_dc, dict) else _clone(_EMPTY_SLA_BY_DC)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return _clone(_EMPTY_SLA_BY_DC)


def get_dc_s3_pools(dc_code: str, tr: Optional[dict]) -> dict:
    try:
        enc = quote(dc_code, safe="")
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/s3/pools", params=_build_time_params(tr))
        return data if isinstance(data, dict) else {"pools": [], "latest": {}, "growth": {}}
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return {"pools": [], "latest": {}, "growth": {}}


def get_customer_s3_vaults(customer_name: str, tr: Optional[dict]) -> dict:
    try:
        enc = quote(customer_name, safe="")
        data = _get_json(_client_cust, f"/api/v1/customers/{enc}/s3/vaults", params=_build_time_params(tr))
        return data if isinstance(data, dict) else {"vaults": [], "latest": {}, "growth": {}}
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return {"vaults": [], "latest": {}, "growth": {}}


def get_dc_netbackup_pools(dc_code: str, tr: Optional[dict]) -> dict:
    try:
        enc = quote(dc_code, safe="")
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/backup/netbackup", params=_build_time_params(tr))
        return data if isinstance(data, dict) else {"pools": [], "rows": []}
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return {"pools": [], "rows": []}


def get_dc_zerto_sites(dc_code: str, tr: Optional[dict]) -> dict:
    try:
        enc = quote(dc_code, safe="")
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/backup/zerto", params=_build_time_params(tr))
        return data if isinstance(data, dict) else {"sites": [], "rows": []}
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return {"sites": [], "rows": []}


def get_dc_veeam_repos(dc_code: str, tr: Optional[dict]) -> dict:
    try:
        enc = quote(dc_code, safe="")
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/backup/veeam", params=_build_time_params(tr))
        return data if isinstance(data, dict) else {"repos": [], "rows": []}
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return {"repos": [], "rows": []}


def get_classic_cluster_list(dc_code: str, tr: Optional[dict]) -> list[str]:
    try:
        enc = quote(dc_code, safe="")
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/clusters/classic", params=_build_time_params(tr))
        return data if isinstance(data, list) else []
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return []


def get_hyperconv_cluster_list(dc_code: str, tr: Optional[dict]) -> list[str]:
    try:
        enc = quote(dc_code, safe="")
        data = _get_json(
            _client_dc,
            f"/api/v1/datacenters/{enc}/clusters/hyperconverged",
            params=_build_time_params(tr),
        )
        return data if isinstance(data, list) else []
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return []


def _clusters_param(selected: Optional[list[str]]) -> dict[str, str]:
    if not selected:
        return {}
    return {"clusters": ",".join(selected)}


def get_classic_metrics_filtered(
    dc_code: str, selected_clusters: Optional[list[str]], tr: Optional[dict]
) -> dict:
    try:
        enc = quote(dc_code, safe="")
        params = {**_build_time_params(tr), **_clusters_param(selected_clusters)}
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/compute/classic", params=params)
        return data if isinstance(data, dict) else {}
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return {}


def get_hyperconv_metrics_filtered(
    dc_code: str, selected_clusters: Optional[list[str]], tr: Optional[dict]
) -> dict:
    try:
        enc = quote(dc_code, safe="")
        params = {**_build_time_params(tr), **_clusters_param(selected_clusters)}
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/compute/hyperconverged", params=params)
        return data if isinstance(data, dict) else {}
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return {}


def get_physical_inventory_dc(dc_name: str) -> dict:
    try:
        enc = quote(dc_name, safe="")
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/physical-inventory")
        return data if isinstance(data, dict) else {"total": 0, "by_role": [], "by_role_manufacturer": []}
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return {"total": 0, "by_role": [], "by_role_manufacturer": []}


def get_physical_inventory_overview_by_role() -> list[dict]:
    try:
        data = _get_json(_client_dc, "/api/v1/physical-inventory/overview/by-role")
        return data if isinstance(data, list) else []
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return []


def get_physical_inventory_overview_manufacturer(role: str) -> list[dict]:
    try:
        enc = quote(role, safe="")
        data = _get_json(_client_dc, "/api/v1/physical-inventory/overview/manufacturer", params={"role": enc})
        return data if isinstance(data, list) else []
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return []


def get_physical_inventory_overview_location(role: str, manufacturer: str) -> list[dict]:
    try:
        data = _get_json(
            _client_dc,
            "/api/v1/physical-inventory/overview/location",
            params={"role": role, "manufacturer": manufacturer},
        )
        return data if isinstance(data, list) else []
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return []


def get_physical_inventory_customer() -> list[dict]:
    try:
        data = _get_json(_client_dc, "/api/v1/physical-inventory/customer")
        return data if isinstance(data, list) else []
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return []


# ---------------------------------------------------------------------------
# Network > SAN (Brocade) + Power Mimari Storage (IBM)
# ---------------------------------------------------------------------------


def get_dc_san_switches(dc_code: str, tr: Optional[dict]) -> list[str]:
    try:
        enc = quote(dc_code, safe="")
        params = _build_time_params(tr)
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/san/switches", params=params)
        return data if isinstance(data, list) else []
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return []


def get_dc_san_port_usage(dc_code: str, tr: Optional[dict]) -> dict:
    try:
        enc = quote(dc_code, safe="")
        params = _build_time_params(tr)
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/san/port-usage", params=params)
        return data if isinstance(data, dict) else {}
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return {}


def get_dc_san_health(dc_code: str, tr: Optional[dict]) -> list[dict]:
    try:
        enc = quote(dc_code, safe="")
        params = _build_time_params(tr)
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/san/health", params=params)
        return data if isinstance(data, list) else []
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return []


def get_dc_san_traffic_trend(dc_code: str, tr: Optional[dict]) -> list[dict]:
    try:
        enc = quote(dc_code, safe="")
        params = _build_time_params(tr)
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/san/traffic-trend", params=params)
        return data if isinstance(data, list) else []
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return []


def get_dc_san_bottleneck(dc_code: str, tr: Optional[dict]) -> dict:
    try:
        enc = quote(dc_code, safe="")
        params = _build_time_params(tr)
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/san/bottleneck", params=params)
        return data if isinstance(data, dict) else {}
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return {}


def get_dc_storage_capacity(dc_code: str, tr: Optional[dict]) -> dict:
    try:
        enc = quote(dc_code, safe="")
        params = _build_time_params(tr)
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/storage/capacity", params=params)
        return data if isinstance(data, dict) else {}
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return {}


def get_dc_storage_performance(dc_code: str, tr: Optional[dict]) -> dict:
    try:
        enc = quote(dc_code, safe="")
        params = _build_time_params(tr)
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/storage/performance", params=params)
        return data if isinstance(data, dict) else {}
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return {}


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
    try:
        enc = quote(dc_code, safe="")
        params = _build_time_params(tr)
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/network/filters", params=params)
        return data if isinstance(data, dict) else {}
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return {}


def get_dc_network_port_summary(
    dc_code: str,
    tr: Optional[dict],
    manufacturer: Optional[str] = None,
    device_role: Optional[str] = None,
    device_name: Optional[str] = None,
) -> dict:
    try:
        enc = quote(dc_code, safe="")
        params = _build_optional_params(
            _build_time_params(tr),
            manufacturer=manufacturer,
            device_role=device_role,
            device_name=device_name,
        )
        data = _get_json(
            _client_dc,
            f"/api/v1/datacenters/{enc}/network/port-summary",
            params=params,
        )
        return data if isinstance(data, dict) else {}
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return {}


def get_dc_network_95th_percentile(
    dc_code: str,
    tr: Optional[dict],
    top_n: int = 20,
    manufacturer: Optional[str] = None,
    device_role: Optional[str] = None,
    device_name: Optional[str] = None,
) -> dict:
    try:
        enc = quote(dc_code, safe="")
        params = _build_optional_params(
            _build_time_params(tr),
            top_n=top_n,
            manufacturer=manufacturer,
            device_role=device_role,
            device_name=device_name,
        )
        data = _get_json(
            _client_dc,
            f"/api/v1/datacenters/{enc}/network/95th-percentile",
            params=params,
        )
        return data if isinstance(data, dict) else {}
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return {}


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
    try:
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
        data = _get_json(
            _client_dc,
            f"/api/v1/datacenters/{enc}/network/interface-table",
            params=params,
        )
        return data if isinstance(data, dict) else {}
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return {}


def get_dc_zabbix_storage_capacity(dc_code: str, tr: Optional[dict], host: Optional[str] = None) -> dict:
    try:
        enc = quote(dc_code, safe="")
        params = _build_optional_params(_build_time_params(tr), host=host)
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/zabbix-storage/capacity", params=params)
        return data if isinstance(data, dict) else {}
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return {}


def get_dc_zabbix_storage_trend(dc_code: str, tr: Optional[dict], host: Optional[str] = None) -> dict:
    try:
        enc = quote(dc_code, safe="")
        params = _build_optional_params(_build_time_params(tr), host=host)
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/zabbix-storage/trend", params=params)
        return data if isinstance(data, dict) else {}
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return {}


def get_dc_zabbix_storage_devices(dc_code: str, tr: Optional[dict]) -> list[dict]:
    try:
        enc = quote(dc_code, safe="")
        params = _build_time_params(tr)
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/zabbix-storage/devices", params=params)
        return data if isinstance(data, list) else []
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return []


def get_dc_zabbix_disk_list(dc_code: str, tr: Optional[dict], host: Optional[str] = None) -> dict:
    if host is None:
        return {"items": []}
    try:
        enc = quote(dc_code, safe="")
        params = _build_optional_params(_build_time_params(tr), host=host)
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/zabbix-storage/disk-list", params=params)
        return data if isinstance(data, dict) else {"items": []}
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return {"items": []}


def get_dc_zabbix_disk_trend(
    dc_code: str,
    tr: Optional[dict],
    host: Optional[str] = None,
    disk_name: Optional[str] = None,
) -> dict:
    if host is None or disk_name is None:
        return {"series": []}
    try:
        enc = quote(dc_code, safe="")
        params = _build_optional_params(_build_time_params(tr), host=host, disk=disk_name)
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/zabbix-storage/disk-trend", params=params)
        return data if isinstance(data, dict) else {"series": []}
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return {"series": []}


def get_dc_zabbix_disk_health(dc_code: str, tr: Optional[dict]) -> dict:
    try:
        enc = quote(dc_code, safe="")
        params = _build_time_params(tr)
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/zabbix-storage/disk-health", params=params)
        return data if isinstance(data, dict) else {}
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return {}


def get_dc_racks(dc_code: str) -> dict:
    try:
        enc = quote(dc_code, safe="")
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc}/racks")
        return data if isinstance(data, dict) else {"racks": [], "summary": {}}
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return {"racks": [], "summary": {}}


def get_rack_devices(dc_code: str, rack_name: str) -> dict:
    try:
        enc_dc = quote(dc_code, safe="")
        enc_rack = quote(rack_name, safe="")
        data = _get_json(_client_dc, f"/api/v1/datacenters/{enc_dc}/racks/{enc_rack}/devices")
        return data if isinstance(data, dict) else {"devices": []}
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return {"devices": []}
