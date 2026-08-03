"""Customer Backup zero-delay + unique-jobs URL resolution + DC attribution."""
from __future__ import annotations

from unittest.mock import patch

import dash
from dash import dcc, html

from shared.backup.dc_attribution import (
    annotate_unique_job_dc,
    collect_datacenter_codes,
    extract_dc_code,
)
from shared.backup.unique_jobs import normalize_unique_job_row
from shared.customer.cache_keys import CUSTOMER_ASSETS_CACHE_VERSION
from src.components.backup_unique_jobs_panel import _extract_customer_name
from src.pages import customer_view as cv
from tests.test_customer_view_tab_sections import _tr


def _walk(node):
    yield node
    children = getattr(node, "children", None)
    if isinstance(children, (list, tuple)):
        for c in children:
            yield from _walk(c)
    elif children is not None:
        yield from _walk(children)


def _ids(node):
    return {getattr(n, "id", None) for n in _walk(node)}


def test_customer_assets_cache_version_bumped_for_replica_split():
    assert CUSTOMER_ASSETS_CACHE_VERSION == "replica-split-v5"


def test_shell_has_single_backup_category_store():
    """Category store lives outside page-root (layout shell), not inside render_customer_shell."""
    shell = cv.render_customer_shell("Acme", _tr(), None, perspective=cv.PERSPECTIVE_MANAGER)
    assert "customer-backup-category-tab-store" not in _ids(shell)
    layout = cv.build_customer_layout_shell(selected_customer="Acme", time_range=_tr())
    assert "customer-backup-category-tab-store" in _ids(layout)


def test_extract_customer_name_from_query_string():
    assert _extract_customer_name("/customer-view", "?customer=Boyner") == "Boyner"
    assert _extract_customer_name("/customer-view", "customer=Acme%20Corp") == "Acme Corp"
    assert _extract_customer_name("/customer-view", "") is None
    assert _extract_customer_name("/customer/Legacy", None) == "Legacy"


def test_apply_customer_backup_category_maps_veeam_to_replication():
    # Direct function body (Dash wraps callbacks); call the undecorated logic.
    from dash.exceptions import PreventUpdate
    from src.pages import customer_view_callbacks as cvc

    fn = cvc.apply_customer_backup_category
    # Dash may wrap; prefer .__wrapped__ when present.
    target = getattr(fn, "__wrapped__", fn)
    assert target("veeam") == "replication"
    assert target("zerto") == "replication"
    assert target("image") == "image"
    try:
        target("")
        raised = False
    except PreventUpdate:
        raised = True
    assert raised


def test_tab_veeam_uses_metrics_grid_not_undefined_kpi_strip():
    """Regression: NameError _kpi_strip when opening Customer Backup Replication."""
    out = cv._tab_veeam(
        {
            "veeam": {
                "session_types": [{"type": "Replica", "count": 2}],
                "session_type_buckets": {"replica": [{"type": "Replica", "count": 2}], "backup": []},
            }
        },
        {"veeam_defined_sessions": 5},
        crm_eff_panel=None,
    )
    assert out is not None
    text = str(out)
    assert "Defined sessions" in text
    assert "Session types" in text


def test_render_backup_tab_cache_miss_returns_preparing_shell():
    with patch.object(cv.api, "peek_customer_resources", return_value=None), \
         patch("src.services.app_background_warm.trigger_customer_view_warm") as warm:
        out = cv.render_backup_tab("Acme", _tr(), cv.PERSPECTIVE_MANAGER)
    warm.assert_called_once()
    assert "cust-backup-preparing" in _ids(out) or "cust-backup-warm-retry" in _ids(out)


def test_render_backup_tab_cache_hit_renders_without_cold_fetch():
    payload = {
        "totals": {"backup": {}},
        "assets": {"backup": {}, "classic": {"replica_vm_list": []}, "hyperconv": {"replica_vm_list": []}},
    }
    with patch.object(cv.api, "peek_customer_resources", return_value=payload), \
         patch.object(cv.api, "get_customer_resources") as cold, \
         patch.object(cv.api, "get_customer_efficiency_by_category", return_value=[]), \
         patch.object(cv.api, "get_customer_nutanix_snapshots", return_value={"rows": []}), \
         patch.object(cv, "_collect_customer_job_kpi_bundle", return_value={}):
        out = cv.render_backup_tab("Acme", _tr(), cv.PERSPECTIVE_MANAGER)
    cold.assert_not_called()
    assert out is not None


def test_extract_dc_code_from_site_labels():
    assert extract_dc_code("DC13-SiteKM") == "DC13"
    assert extract_dc_code("nbmediadc14.blt.vc") == "DC14"
    assert extract_dc_code("10.34.2.104") is None


def test_normalize_unique_job_row_annotates_dc():
    row = normalize_unique_job_row(
        {"name": "vpg1", "status": "Success", "source_site": "DC13-SiteKM"}
    )
    assert row["status"] == "success"
    assert row["dc"] == "DC13"
    assert collect_datacenter_codes([row]) == ["DC13"]


def test_annotate_unique_job_dc_preserves_existing():
    out = annotate_unique_job_dc({"dc": "az11", "source_site": "DC13-Site"})
    assert out["dc"] == "AZ11"
