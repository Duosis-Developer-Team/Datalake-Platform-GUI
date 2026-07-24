"""dc_hosting_u total/allocated come from the shared occupancy module, summed
over the DC pattern. total=Σ capacity_u, allocated=Σ used_u."""
from unittest.mock import MagicMock, patch

from app.services.sellable_service import SellableService
from shared.sellable.models import InfraSource


def _service():
    svc = SellableService(
        customer_service=MagicMock(),
        webui=MagicMock(),
        config_service=MagicMock(),
        currency_service=MagicMock(),
        tagging_service=MagicMock(),
    )
    return svc


def test_query_total_allocated_routes_dc_hosting_u_to_colocation():
    svc = _service()
    src = InfraSource(
        panel_key="dc_hosting_u", dc_code="*",
        source_table="__colocation_occupancy__", total_column="capacity_u",
        allocated_table="__colocation_occupancy__", allocated_column="used_u",
    )
    with patch.object(svc, "_query_colocation_totals", return_value=(3616.0, 1817.0)) as q:
        total, alloc = svc._query_total_allocated(src, "DC13")
    q.assert_called_once_with(src, "DC13")
    assert (total, alloc) == (3616.0, 1817.0)


def test_query_colocation_totals_sums_occupancy_rows():
    svc = _service()
    src = InfraSource(panel_key="dc_hosting_u", dc_code="*")
    rows = [
        {"capacity_u": 47, "used_u": 35, "free_u": 12},
        {"capacity_u": 47, "used_u": 20, "free_u": 27},
    ]
    # _get_connection() is a context manager yielding a conn with .cursor()
    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.cursor.return_value.__enter__.return_value = MagicMock()
    svc._svc._get_connection.return_value = conn
    svc._dc_pattern = lambda dc: "%DC13%"
    with patch("app.services.sellable_service.coloc_occ.occupancy_rows", return_value=rows):
        total, alloc = svc._query_colocation_totals(src, "DC13")
    assert total == 94.0     # 47 + 47
    assert alloc == 55.0     # 35 + 20
