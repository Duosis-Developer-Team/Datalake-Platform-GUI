"""dc_hosting_u total/allocated come from the shared occupancy module, summed
over the DC pattern -- restricted to SELLABLE racks: total=Σ capacity_u,
allocated=Σ used_u over racks whose role is neither NETWORK (1) nor
colocation (3/4). Customer rule 2026-08-04."""
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


def _totals(svc, src, rows):
    # _get_connection() is a context manager yielding a conn with .cursor()
    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.cursor.return_value.__enter__.return_value = MagicMock()
    svc._svc._get_connection.return_value = conn
    svc._dc_pattern = lambda dc: "%DC13%"
    with patch("app.services.sellable_service.coloc_occ.occupancy_rows", return_value=rows):
        return svc._query_colocation_totals(src, "DC13")


def test_query_colocation_totals_sums_occupancy_rows():
    """Rows with no role at all (informational callers) stay counted -- an
    absent role is unclassified, not network."""
    svc = _service()
    src = InfraSource(panel_key="dc_hosting_u", dc_code="*")
    rows = [
        {"capacity_u": 47, "used_u": 35, "free_u": 12},
        {"capacity_u": 47, "used_u": 20, "free_u": 27},
    ]
    total, alloc = _totals(svc, src, rows)
    assert total == 94.0     # 47 + 47
    assert alloc == 55.0     # 35 + 20


def test_query_colocation_totals_excludes_network_and_customer_racks():
    """The defect the customer reported: every rack fed the priced total, so
    switching cabinets and cabinets already sold to a colocation customer
    were being offered for sale a second time."""
    svc = _service()
    src = InfraSource(panel_key="dc_hosting_u", dc_code="*")
    rows = [
        {"role_id": "2", "capacity_u": 47, "used_u": 20, "free_u": 27},   # HOST
        {"role_id": "1", "capacity_u": 47, "used_u": 30, "free_u": 17},   # NETWORK
        {"role_id": "4", "capacity_u": 42, "used_u": 10, "free_u": 32},   # CUSTOMER
        {"role_id": "3", "capacity_u": 42, "used_u": 5, "free_u": 37},    # NON-STANDART
    ]
    total, alloc = _totals(svc, src, rows)
    assert total == 47.0
    assert alloc == 20.0


def test_query_colocation_totals_drops_non_sellable_from_total_not_just_allocated():
    """Regression guard on the shape of the fix, not just its direction.

    Keeping a non-sellable rack's capacity in `total` while counting its
    occupancy in `allocated` also reduces the headroom, so a mutant that only
    filtered one side would still look "smaller". But it produces a different
    number, because the CRM threshold is a percentage OF total: measured
    2026-08-04, all-racks 8,603/2,712 gives 4,170.4 sellable U, half-filtered
    gives 1,890.4, and the correct sellable-only 4,894/1,283 gives 2,632.2.
    """
    svc = _service()
    src = InfraSource(panel_key="dc_hosting_u", dc_code="*")
    rows = [
        {"role_id": "2", "capacity_u": 4894, "used_u": 1283, "free_u": 3611},
        {"role_id": "1", "capacity_u": 1450, "used_u": 584, "free_u": 866},
        {"role_id": "4", "capacity_u": 1925, "used_u": 808, "free_u": 1117},
        {"role_id": "3", "capacity_u": 334, "used_u": 37, "free_u": 297},
    ]
    total, alloc = _totals(svc, src, rows)
    assert (total, alloc) == (4894.0, 1283.0)
    # total x 80% - allocated, the panel's own arithmetic
    assert round(total * 0.8 - alloc, 1) == 2632.2
