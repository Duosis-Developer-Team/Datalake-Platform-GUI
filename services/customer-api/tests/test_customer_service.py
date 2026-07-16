from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from psycopg2 import OperationalError

from app.db.queries import customer as cq
from app.services.customer_service import (
    CUSTOMER_DATA_CACHE_TTL_COLD,
    CUSTOMER_DATA_CACHE_TTL_HOT,
    CLUSTER_ARCH_MAP_TTL_SECONDS,
    CustomerService,
)


def test_get_customer_list_empty_without_db_and_no_env(monkeypatch):
    monkeypatch.delenv("WARMED_CUSTOMERS", raising=False)
    with patch("app.services.customer_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = CustomerService()
    assert svc.get_customer_list() == []


def test_get_customer_list_loads_crm_project_customers(monkeypatch):
    monkeypatch.delenv("WARMED_CUSTOMERS", raising=False)

    class _CursorCtx:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    class _ConnCtx:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return _CursorCtx()

    def _run_rows_side_effect(_cur, sql, params=None):
        if sql == cq.CRM_PROJECT_CUSTOMER_LIST:
            return [("Acme Corp",), ("Beta Ltd",)]
        return []

    def _run_row_side_effect(_cur, sql, params=None):
        if sql == cq.CRM_BOYNER_ACCOUNT_NAME:
            return ("BOYNER BUYUK MAGAZACILIK A.S.",)
        return None

    with patch("app.services.customer_service.pg_pool.ThreadedConnectionPool", return_value=object()):
        svc = CustomerService()
    svc._pool = object()

    with patch.object(svc, "_get_connection", return_value=_ConnCtx()), \
         patch.object(svc, "_run_rows", side_effect=_run_rows_side_effect), \
         patch.object(svc, "_run_row", side_effect=_run_row_side_effect):
        result = svc.get_customer_list()

    assert "Acme Corp" in result
    assert "Beta Ltd" in result
    assert "BOYNER BUYUK MAGAZACILIK A.S." in result
    assert "Boyner" not in result


def test_customers_for_cache_rebuild_returns_pinned_only(monkeypatch):
    monkeypatch.setenv("WARMED_CUSTOMERS", "Acme, Beta")
    with patch("app.services.customer_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = CustomerService()
    monkeypatch.setattr(svc, "_load_cache_pinned_display_names", lambda: ("VIP Corp",))
    assert svc._customers_for_cache_rebuild() == ("VIP Corp",)


def test_customers_for_cache_rebuild_includes_vip_display_names(monkeypatch):
    monkeypatch.delenv("WARMED_CUSTOMERS", raising=False)
    with patch("app.services.customer_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = CustomerService()
    monkeypatch.setattr(svc, "_load_cache_pinned_display_names", lambda: ("VIP Corp",))
    names = svc._customers_for_cache_rebuild()
    assert names == ("VIP Corp",)


def test_mapped_non_vip_customers_for_warm_excludes_vip_and_unmapped(monkeypatch):
    monkeypatch.delenv("WARMED_CUSTOMERS", raising=False)
    with patch("app.services.customer_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = CustomerService()
    svc._pool = object()
    monkeypatch.setattr(
        "app.services.customer_service.load_project_customer_rows",
        lambda *_a, **_k: type("R", (), {"rows": [
            {"crm_accountid": "a1", "crm_account_name": "Boyner Holding"},
            {"crm_accountid": "a2", "crm_account_name": "Alpha Corp"},
            {"crm_accountid": "a3", "crm_account_name": "VIP Corp"},
        ]})(),
    )
    monkeypatch.setattr(
        svc,
        "_load_profile_flags_index",
        lambda: {
            "a3": {"is_vip": True, "cache_pinned": True},
        },
    )
    monkeypatch.setattr(
        svc,
        "_load_source_mapping_index",
        lambda: {
            "a1": [{"enabled": True, "match_value": "Boyner"}],
            "a2": [],
            "a3": [{"enabled": True, "match_value": "VIP"}],
        },
    )
    names = svc._mapped_non_vip_customers_for_warm()
    assert names == ("Boyner Holding",)


def test_refresh_all_data_rebuilds_hot_tier_only(monkeypatch):
    with patch("app.services.customer_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = CustomerService()
    svc._pool = object()
    calls: list[str] = []

    monkeypatch.setattr(
        svc,
        "_rebuild_customer_caches_for_warmed_customers",
        lambda: calls.append("hot"),
    )
    monkeypatch.setattr(
        svc,
        "refresh_warm_tier_caches",
        lambda: calls.append("warm"),
    )
    svc.refresh_all_data()
    assert calls == ["hot"]


def test_warm_mapped_non_vip_batch_skips_when_already_running(monkeypatch):
    with patch("app.services.customer_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = CustomerService()
    svc._pool = object()
    monkeypatch.setattr(svc, "_batch_warm_already_running", lambda: True)
    monkeypatch.setattr(
        svc,
        "_rebuild_customer_caches_for_customer",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("should not run")),
    )
    svc.warm_mapped_non_vip_batch()


def test_warm_mapped_non_vip_batch_calls_customers_sequentially(monkeypatch):
    with patch("app.services.customer_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = CustomerService()
    svc._pool = object()
    order: list[str] = []
    monkeypatch.setattr(svc, "_mapped_non_vip_customers_for_warm", lambda: ("Alpha", "Beta"))
    monkeypatch.setattr(
        svc,
        "_rebuild_customer_caches_for_customer",
        lambda name, cache_ttl=None: order.append(name),
    )
    monkeypatch.setattr("app.services.customer_service.time.sleep", lambda _s: None)
    monkeypatch.setattr("app.services.customer_service.cache.set", lambda *_a, **_k: None)
    svc.warm_mapped_non_vip_batch()
    assert order == ["Alpha", "Beta"]


def test_customer_cache_ttl_constants_match_adr():
    assert CUSTOMER_DATA_CACHE_TTL_HOT == 3600
    assert CUSTOMER_DATA_CACHE_TTL_COLD == 3600
    assert CLUSTER_ARCH_MAP_TTL_SECONDS == 3600


def test_get_customer_resources_returns_last_good_on_db_error():
    mock_pool = MagicMock()
    stale_payload = {"totals": {"vm": 1}, "assets": {}}
    with patch("app.services.customer_service.pg_pool.ThreadedConnectionPool", return_value=mock_pool):
        svc = CustomerService()
    with patch("app.services.customer_service.cache.run_singleflight", side_effect=OperationalError("ssl eof")), \
         patch("app.services.customer_service.cache.get_stale", return_value=stale_payload), \
         patch("app.services.customer_service.cache.get", return_value=None), \
         patch("app.services.customer_service.cache.get_last_good", return_value=stale_payload):
        out = svc.get_customer_resources("Boyner")
    assert out == stale_payload


def test_set_customer_vip_starts_background_warm_when_display_name_known(monkeypatch):
    webui = MagicMock()
    webui.is_available = True
    with patch("app.services.customer_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = CustomerService()
    svc.attach_webui_pool(webui)
    started: list[str] = []

    class _Thread:
        def __init__(self, target=None, kwargs=None, name=None, daemon=None):
            self._target = target
            self._kwargs = kwargs or {}

        def start(self):
            started.append(self._kwargs.get("customer_name", ""))

    monkeypatch.setattr("app.services.customer_service.threading.Thread", _Thread)
    monkeypatch.setattr(svc, "_display_name_for_account", lambda _aid: "VIP Corp")
    svc.set_customer_vip("acc-1", is_vip=True, updated_by="tester")
    assert started == ["VIP Corp"]


def test_rebuild_customer_caches_for_customer_tracks_failures(monkeypatch):
    with patch("app.services.customer_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = CustomerService()
    monkeypatch.setattr(
        "app.services.customer_service.cache_time_ranges",
        lambda: [{"preset": "7d", "start": "a", "end": "b"}],
    )

    def _boom_resources(*_a, **_k):
        raise RuntimeError("timeout")

    monkeypatch.setattr(svc, "get_customer_resources", _boom_resources)
    monkeypatch.setattr(svc, "get_customer_s3_vaults", lambda *_a, **_k: None)
    # Unique-jobs warming (3 vendors) runs once per customer regardless of the
    # cache_time_ranges() loop above — stub it out so this test stays focused
    # on the resources/s3 failure-tracking behavior it was written to cover.
    monkeypatch.setattr(svc, "get_customer_unique_jobs", lambda *_a, **_k: {})
    summary = svc._rebuild_customer_caches_for_customer("VIP Corp", cache_ttl=3600)
    assert summary["failed"] == 1
    assert summary["ok"] == 4  # s3 (1) + unique-jobs warm (3 vendors)
    assert summary["errors"][0]["target"] == "resources"


def test_set_customer_vip_upserts_profile_flags():
    webui = MagicMock()
    webui.is_available = True
    with patch("app.services.customer_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = CustomerService()
    svc.attach_webui_pool(webui)
    out = svc.set_customer_vip("acc-1", is_vip=True, updated_by="tester")
    webui.execute.assert_called_once()
    args = webui.execute.call_args[0]
    assert args[1] == ("acc-1", True, True, "tester")
    assert out == {
        "status": "ok",
        "crm_accountid": "acc-1",
        "is_vip": True,
        "cache_pinned": True,
    }


def test_set_customer_vip_clears_cache_pinned_when_not_vip():
    webui = MagicMock()
    webui.is_available = True
    with patch("app.services.customer_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = CustomerService()
    svc.attach_webui_pool(webui)
    out = svc.set_customer_vip("acc-2", is_vip=False)
    args = webui.execute.call_args[0]
    assert args[1] == ("acc-2", False, False, None)
    assert out["is_vip"] is False
    assert out["cache_pinned"] is False


def test_set_customer_vip_requires_webui_pool():
    with patch("app.services.customer_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = CustomerService()
    with pytest.raises(RuntimeError, match="WebUI pool not configured"):
        svc.set_customer_vip("acc-1", is_vip=True)


def test_resolve_infra_search_name_uses_boyner_for_crm_display_name(monkeypatch):
    with patch("app.services.customer_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = CustomerService()
    svc._netbox_tenant_names = ["Boyner"]
    assert svc.resolve_infra_search_name("BOYNER BUYUK MAGAZACILIK A.S.") == "Boyner"


def test_get_customer_resources_returns_empty_when_pool_none():
    with patch("app.services.customer_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = CustomerService()
    assert svc._pool is None
    result = svc.get_customer_resources("Boyner")
    assert "totals" in result
    assert "assets" in result
    assert result["totals"]["vms_total"] == 0


def test_get_customer_resources_totals_structure_when_pool_none():
    with patch("app.services.customer_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = CustomerService()
    result = svc.get_customer_resources("Boyner")
    totals = result["totals"]
    assert "intel_vms_total" in totals
    assert "classic_vms_total" in totals
    assert "hyperconv_vms_total" in totals
    assert "pure_nutanix_vms_total" in totals
    assert "power_lpar_total" in totals
    assert "backup" in totals


def test_get_customer_resources_assets_structure_when_pool_none():
    with patch("app.services.customer_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = CustomerService()
    result = svc.get_customer_resources("Boyner")
    assets = result["assets"]
    assert "intel" in assets
    assert "classic" in assets
    assert "hyperconv" in assets
    assert "pure_nutanix" in assets
    assert "power" in assets
    assert "backup" in assets


def test_pool_is_none_when_db_unavailable():
    with patch("app.services.customer_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = CustomerService()
    assert svc._pool is None


def test_get_cluster_arch_map_does_not_cache_when_pool_none():
    with patch("app.services.customer_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = CustomerService()

    with patch("app.services.customer_service.time_range_to_bounds", return_value=("start-ts", "end-ts")), \
         patch("app.services.customer_service.cache.run_singleflight") as sf_mock:
        result = svc._get_cluster_arch_map({"preset": "7d"})

    assert result == {"managed_nutanix": [], "pure_nutanix": []}
    sf_mock.assert_not_called()


def test_get_cluster_arch_map_uses_latest_fallback_when_range_clusters_missing():
    with patch("app.services.customer_service.pg_pool.ThreadedConnectionPool", side_effect=OperationalError("no db")):
        svc = CustomerService()
    svc._pool = object()

    class _CursorCtx:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    class _ConnCtx:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return _CursorCtx()

    def _run_rows_side_effect(_cur, sql, params=None):
        if sql == cq.ALL_VMWARE_CLUSTER_NAMES:
            return [("vmw-cluster", "hyperconv")]
        if sql == cq.ALL_NUTANIX_CLUSTER_NAMES:
            return []
        if sql == cq.ALL_NUTANIX_CLUSTER_NAMES_LATEST:
            return [("ntx-cluster", "uuid-1")]
        return []

    with patch.object(svc, "_get_connection", return_value=_ConnCtx()), \
         patch.object(svc, "_run_rows", side_effect=_run_rows_side_effect) as run_rows_mock, \
         patch("app.services.customer_service.time_range_to_bounds", return_value=("start-ts", "end-ts")), \
         patch("app.core.cache_backend.cache_get", return_value=None), \
         patch("app.core.cache_backend.cache_set"), \
         patch("app.services.customer_service.build_cluster_arch_map", return_value={"managed_nutanix": ["ntx-cluster"], "pure_nutanix": []}):
        result = svc._get_cluster_arch_map({"preset": "7d"})

    assert result == {"managed_nutanix": ["ntx-cluster"], "pure_nutanix": []}
    queried_sql = [call.args[1] for call in run_rows_mock.call_args_list]
    assert cq.ALL_NUTANIX_CLUSTER_NAMES in queried_sql
    assert cq.ALL_NUTANIX_CLUSTER_NAMES_LATEST in queried_sql


def test_get_customer_resources_raises_503_when_db_error_not_cached():
    mock_pool = MagicMock()
    with patch("app.services.customer_service.pg_pool.ThreadedConnectionPool", return_value=mock_pool):
        svc = CustomerService()
    with patch("app.services.customer_service.cache.run_singleflight", side_effect=OperationalError("ssl eof")), \
         patch("app.services.customer_service.cache.get_stale", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            svc.get_customer_resources("Boyner")
    assert exc_info.value.status_code == 503


def test_get_connection_discards_pool_conn_on_fatal_operational_error():
    mock_pool = MagicMock()
    conn = MagicMock()
    mock_pool.getconn.return_value = conn
    with patch("app.services.customer_service.pg_pool.ThreadedConnectionPool", return_value=mock_pool):
        svc = CustomerService()

    with pytest.raises(OperationalError):
        with svc._get_connection():
            raise OperationalError("SSL SYSCALL error: EOF detected")

    mock_pool.putconn.assert_called_once_with(conn, close=True)


def test_get_connection_returns_conn_to_pool_on_statement_timeout():
    mock_pool = MagicMock()
    conn = MagicMock()
    mock_pool.getconn.return_value = conn
    with patch("app.services.customer_service.pg_pool.ThreadedConnectionPool", return_value=mock_pool):
        svc = CustomerService()

    err = OperationalError("canceling statement due to statement timeout")
    with pytest.raises(OperationalError):
        with svc._get_connection():
            raise err

    mock_pool.putconn.assert_called_once_with(conn, close=False)
