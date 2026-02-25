import os

import requests

_QUERY_URL = os.getenv("QUERY_SERVICE_URL", "http://query-service:8002")
_HEADERS = {"X-Internal-Key": os.getenv("INTERNAL_API_KEY", "")}
_TIMEOUT = 120  # query-service cold start ~74s


def get_summary() -> list[dict]:
    """GET /datacenters/summary → list[DCSummary]"""
    r = requests.get(
        f"{_QUERY_URL}/datacenters/summary",
        headers=_HEADERS,
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def get_dc_detail(dc_code: str) -> dict:
    """GET /datacenters/{dc_code} → DCDetail"""
    r = requests.get(
        f"{_QUERY_URL}/datacenters/{dc_code}",
        headers=_HEADERS,
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()
