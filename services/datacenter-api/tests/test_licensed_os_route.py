"""The licensed-OS DC endpoint must live where the GUI client calls it.

It was registered as `/{dc_code}/licensed-os`, which resolves to
`/api/v1/{dc_code}/licensed-os` — every other DC route carries a `/datacenters`
segment. The client called the conventional path, got 404, and the whole
Lisanslı OS tab rendered zeros with "CRM eşleştirmesi çözülemedi", which reads as
"this datacenter has no licensed guests" rather than "the request 404'd".

A greedy `/{dc_code}/...` at the root of /api/v1 is also a shadowing hazard.
"""
from __future__ import annotations

from app.main import app


def _paths() -> set[str]:
    # Read the OpenAPI schema, not app.routes: routers are included lazily here,
    # so app.routes lists six entries and every assertion below would pass
    # vacuously. This is also the exact path set an HTTP client resolves against.
    return set(app.openapi()["paths"])


def test_endpoint_is_under_the_datacenters_segment():
    assert "/api/v1/datacenters/{dc_code}/licensed-os" in _paths()


def test_the_greedy_root_level_path_is_gone():
    assert "/api/v1/{dc_code}/licensed-os" not in _paths()


def test_it_sits_alongside_the_other_dc_routes():
    """Same shape as its neighbours, so the next person guesses the URL right."""
    assert "/api/v1/datacenters/{dc_code}" in _paths()
