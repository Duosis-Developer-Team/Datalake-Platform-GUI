"""Internal HTTP clients for the existing backend microservices.

Uses ``httpx`` (same library as the Dash frontend ``src/services/api_client.py``)
and forwards the caller's ``Authorization`` header downstream so the existing
``verify_api_user`` dependency on each service keeps working unchanged.

This module is deliberately *generic*: a single ``get_json(service, path, ...)``
keyed by logical service name. The concrete endpoint paths live in the tool
registry, so adding a tool never means touching transport code.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Optional

import httpx

from datalake_tools_core.config import get_settings

settings = get_settings()

logger = logging.getLogger("chatbot-api.api_clients")

# Logical service name -> base URL (Docker/K8s service DNS from settings).
SERVICE_BASE_URLS: dict[str, str] = {
    "datacenter-api": settings.datacenter_api_url.rstrip("/"),
    "customer-api": settings.customer_api_url.rstrip("/"),
    "query-api": settings.query_api_url.rstrip("/"),
    "crm-engine": settings.crm_engine_url.rstrip("/"),
    "admin-api": settings.admin_api_url.rstrip("/"),
}

_HTTP_ERRORS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.TimeoutException,
    httpx.HTTPStatusError,
    httpx.RemoteProtocolError,
)


class InternalAPIError(Exception):
    """Raised when a downstream service call fails (caught per-tool)."""

    def __init__(self, service: str, path: str, detail: str) -> None:
        super().__init__(f"{service}{path}: {detail}")
        self.service = service
        self.path = path
        self.detail = detail


_clients: dict[str, httpx.Client] = {}
_clients_lock = threading.Lock()


def _client_for(service: str) -> httpx.Client:
    base = SERVICE_BASE_URLS.get(service)
    if not base:
        raise InternalAPIError(service, "", "unknown service")
    timeout = httpx.Timeout(
        connect=min(10.0, settings.internal_api_timeout_seconds),
        read=settings.internal_api_timeout_seconds,
        write=min(20.0, settings.internal_api_timeout_seconds),
        pool=min(10.0, settings.internal_api_timeout_seconds),
    )
    with _clients_lock:
        c = _clients.get(service)
        if c is None:
            c = httpx.Client(base_url=base, timeout=timeout)
            _clients[service] = c
        return c


def build_time_params(time_range: Optional[dict]) -> dict[str, str]:
    """Convert the WebUI time-range shape into backend query params.

    Mirrors ``src/services/api_client.py:_build_time_params``.
    """
    if not time_range:
        return {}
    params: dict[str, str] = {}
    preset = time_range.get("preset")
    if preset in {"1h", "1d", "7d", "30d"}:
        params["preset"] = preset
    else:
        start = time_range.get("start")
        end = time_range.get("end")
        if start and end:
            params["start"] = str(start)
            params["end"] = str(end)
    if time_range.get("anchor_latest"):
        params["anchor_latest"] = "true"
    return params


def _auth_headers(auth_header: Optional[str]) -> dict[str, str]:
    if auth_header:
        return {"Authorization": auth_header}
    return {}


def get_json(
    service: str,
    path: str,
    params: Optional[dict[str, str]] = None,
    auth_header: Optional[str] = None,
) -> Any:
    """GET ``path`` on ``service`` and return parsed JSON.

    Raises ``InternalAPIError`` on any transport/HTTP error so the orchestrator
    can degrade gracefully (the chatbot must not crash because one tool failed).
    """
    client = _client_for(service)
    try:
        resp = client.get(path, params=params or None, headers=_auth_headers(auth_header))
        resp.raise_for_status()
        if not resp.content:
            return {}
        return resp.json()
    except _HTTP_ERRORS as exc:
        logger.warning("Internal API call failed: %s%s (%s)", service, path, type(exc).__name__)
        raise InternalAPIError(service, path, type(exc).__name__) from exc
    except ValueError as exc:  # JSON decode
        raise InternalAPIError(service, path, "invalid_json") from exc


def close_all() -> None:
    """Close pooled clients (called on shutdown)."""
    with _clients_lock:
        for c in _clients.values():
            try:
                c.close()
            except Exception:  # pragma: no cover - defensive
                pass
        _clients.clear()
