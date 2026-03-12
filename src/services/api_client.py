import os
from copy import deepcopy
from typing import Any, Optional
from urllib.parse import quote

import httpx


API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")

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

_transport = httpx.HTTPTransport(retries=3)
_client = httpx.Client(base_url=API_BASE_URL, timeout=30.0, transport=_transport)


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


def _get_json(path: str, params: Optional[dict[str, str]] = None) -> Any:
    response = _client.get(path, params=params)
    response.raise_for_status()
    return response.json()


def get_global_dashboard(tr: Optional[dict]) -> dict:
    try:
        data = _get_json("/api/v1/dashboard/overview", params=_build_time_params(tr))
        return data if isinstance(data, dict) else _clone(_EMPTY_DASHBOARD)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return _clone(_EMPTY_DASHBOARD)


def get_all_datacenters_summary(tr: Optional[dict]) -> list[dict]:
    try:
        data = _get_json("/api/v1/datacenters/summary", params=_build_time_params(tr))
        return data if isinstance(data, list) else _clone(_EMPTY_DATACENTERS)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return _clone(_EMPTY_DATACENTERS)


def get_dc_details(dc_id: str, tr: Optional[dict]) -> dict:
    try:
        encoded_dc_id = quote(dc_id, safe="")
        data = _get_json(f"/api/v1/datacenters/{encoded_dc_id}", params=_build_time_params(tr))
        return data if isinstance(data, dict) else _clone(_EMPTY_DC_DETAIL)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return _clone(_EMPTY_DC_DETAIL)


def get_customer_list() -> list[str]:
    try:
        data = _get_json("/api/v1/customers")
        return data if isinstance(data, list) else _clone(_EMPTY_CUSTOMERS)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return _clone(_EMPTY_CUSTOMERS)


def get_customer_resources(name: str, tr: Optional[dict]) -> dict:
    try:
        encoded_name = quote(name, safe="")
        data = _get_json(f"/api/v1/customers/{encoded_name}/resources", params=_build_time_params(tr))
        return data if isinstance(data, dict) else _clone(_EMPTY_CUSTOMER)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return _clone(_EMPTY_CUSTOMER)


def execute_registered_query(key: str, params: str) -> dict:
    try:
        encoded_key = quote(key, safe="")
        data = _get_json(f"/api/v1/queries/{encoded_key}", params={"params": params or ""})
        return data if isinstance(data, dict) else _clone(_EMPTY_QUERY)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError):
        return _clone(_EMPTY_QUERY)
