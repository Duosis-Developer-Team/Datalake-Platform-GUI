"""IBM Power per-frame host rows (/compute/power/hosts).

The frame is the host for the sellable engine, so this endpoint has to satisfy
the same row contract as the Classic/Hyperconverged ones while reporting Power's
own units and admitting what the HMC does not measure.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.db.queries import ibm as iq
from app.services.dc_service import POWER_CORES_PER_PROCUNIT, DatabaseService


# ------------------------------------------------------------- SQL contracts


def test_power_host_rows_sql_takes_latest_sample_per_frame():
    assert "ibm_server_general" in iq.POWER_HOST_ROWS
    assert "DISTINCT ON (server_details_servername)" in iq.POWER_HOST_ROWS
    assert "ORDER BY server_details_servername, time DESC" in iq.POWER_HOST_ROWS


def test_power_lpar_allocation_uses_declared_entitlement_columns():
    """Allocation must be the LPAR entitlement the virt_power panels declare.

    physicalprocessorpool_assignedprocunits is the shared-pool size, not what is
    entitled to partitions; measured 2026-08-02 it runs ~39% higher.
    """
    assert "lpar_processor_entitledprocunits" in iq.POWER_HOST_LPAR_ALLOCATION
    assert "lpar_memory_logicalmem" in iq.POWER_HOST_LPAR_ALLOCATION
    assert "physicalprocessorpool" not in iq.POWER_HOST_LPAR_ALLOCATION


def test_power_lpar_allocation_dedupes_before_summing():
    """DISTINCT ON must run before GROUP BY or a frame is multiplied by samples."""
    sql = iq.POWER_HOST_LPAR_ALLOCATION
    assert sql.index("DISTINCT ON (lparname)") < sql.index("GROUP BY")


# ------------------------------------------------------------ row normalization


def _payload(**kw):
    base = dict(
        frame="G2HV19DC13",
        cpu_cap_cores=352.0,
        cpu_used_cores=229.2,
        mem_cap_gb=8192.0,
        mem_available_gb=55.0,
        alloc={"lpar_count": 6, "cpu_alloc_cores": 288.0, "mem_alloc_gb": 8000.0},
    )
    base.update(kw)
    return DatabaseService._power_host_row_payload(**base)


def test_power_row_reports_cores_not_ghz():
    """cpu_cap_ghz carries cores; ghz_per_core=1 keeps the physical track equal.

    The sellable engine reads cpu_cap_ghz/cpu_alloc_ghz raw and the virt_power
    ratio is expressed in cores, so a GHz conversion here would inflate the axis.
    """
    p = _payload()
    assert p["cpu_cap_ghz"] == 352.0
    assert p["cpu_cap_cores"] == 352.0
    assert p["ghz_per_core"] == 1.0
    assert p["cpu_alloc_ghz"] == p["cpu_alloc_ghz_physical"] == 288.0


def test_power_row_memory_used_is_frame_commitment_not_lpar_rollup():
    """mem_used_gb = total - available (includes firmware reserve); alloc is LPARs."""
    p = _payload()
    assert p["mem_used_gb"] == 8137.0
    assert p["mem_alloc_gb"] == 8000.0
    assert p["mem_used_pct"] == 99.3
    assert p["mem_alloc_pct"] == 97.7


def test_power_row_peak_track_mirrors_the_single_hmc_sample():
    """An absent peak would read as zero usage and manufacture headroom."""
    p = _payload()
    assert p["mem_used_gb_peak"] == p["mem_used_gb"]
    assert p["mem_cap_gb_at_peak"] == p["mem_cap_gb"]
    assert p["mem_peak_util_pct"] == p["mem_used_pct"]
    assert p["cpu_used_ghz_peak"] == p["cpu_used_ghz"]
    assert p["cpu_peak_util_pct"] == p["cpu_used_pct"]
    # No average trio: host_sellable falls back to the peak instead of a zero.
    assert "mem_used_gb_avg" not in p
    assert "cpu_used_ghz_avg" not in p


def test_power_row_storage_is_zero_and_flagged_shared():
    """Array free space is not attributable per frame, so storage leaves the min()."""
    p = _payload()
    assert p["stor_cap_gb"] == 0.0
    assert p["stor_provisioned_gb"] == 0.0
    assert p["km_shared_storage"] is True


def test_power_row_frame_without_lpars_reads_as_fully_free():
    """G2HV4DC14 really has zero partitions; allocation must be 0, not a crash."""
    p = _payload(alloc=None)
    assert p["vm_count"] == 0
    assert p["cpu_alloc_ghz"] == 0.0
    assert p["mem_alloc_gb"] == 0.0
    assert p["cpu_alloc_pct"] == 0.0


def test_power_row_zero_capacity_no_division_error():
    p = _payload(cpu_cap_cores=0.0, cpu_used_cores=0.0, mem_cap_gb=0.0,
                 mem_available_gb=0.0, alloc=None)
    assert p["cpu_used_pct"] == 0.0
    assert p["mem_used_pct"] == 0.0
    assert p["mem_alloc_pct"] == 0.0


def test_power_row_memory_available_above_total_does_not_go_negative():
    p = _payload(mem_cap_gb=1024.0, mem_available_gb=2048.0)
    assert p["mem_used_gb"] == 0.0


# --------------------------------------------------------------- service wiring


def _run_power_rows(frame_rows, alloc_rows, dc_code="DC13"):
    svc = DatabaseService()
    svc._pool = MagicMock()
    conn = MagicMock()
    svc._pool.getconn.return_value = conn
    cur = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    seen: list[tuple] = []

    def fake_run_rows(cursor, query, params):
        seen.append(params)
        return alloc_rows if "ibm_lpar_general" in query else frame_rows

    with patch.object(svc, "_run_rows", side_effect=fake_run_rows), patch(
        "app.services.dc_service.cache.get", return_value=None
    ), patch("app.services.dc_service.cache.run_singleflight") as mock_sf:
        mock_sf.side_effect = lambda key, factory: factory()
        out = svc.get_power_host_rows(dc_code, None, {"start": "2026-07-03", "end": "2026-08-02"})
    return out, seen


def test_get_power_host_rows_converts_units_and_joins_lpar_allocation():
    frame_rows = [
        # procunits, utilized procunits, total MB, available MB
        ("G2HV19DC13", 44.0, 28.65, 8388608.0, 56320.0),
        ("G2HV25DC13", 24.0, 1.26, 4194304.0, 1310720.0),
    ]
    alloc_rows = [
        # frame, lpar count, entitled procunits, logical mem MB
        ("G2HV19DC13", 6, 36.0, 8192000.0),
        ("G2HV25DC13", 4, 5.0, 2796544.0),
    ]
    out, seen = _run_power_rows(frame_rows, alloc_rows)

    assert [p[0] for p in seen] == ["%DC13%", "%DC13%"]
    hosts = {h["host"]: h for h in out["hosts"]}
    assert out["host_count"] == 2
    assert hosts["G2HV19DC13"]["cpu_cap_ghz"] == 44.0 * POWER_CORES_PER_PROCUNIT
    assert hosts["G2HV19DC13"]["cpu_alloc_ghz"] == 36.0 * POWER_CORES_PER_PROCUNIT
    assert hosts["G2HV19DC13"]["mem_cap_gb"] == 8192.0
    assert hosts["G2HV19DC13"]["mem_alloc_gb"] == 8000.0
    assert hosts["G2HV19DC13"]["vm_count"] == 6
    assert hosts["G2HV25DC13"]["cpu_cap_ghz"] == 192.0


def test_get_power_host_rows_frame_missing_from_lpar_table_still_returned():
    """A staged frame with no partitions must appear as capacity, not vanish."""
    out, _ = _run_power_rows(
        [("G2HV4DC14", 128.0, 0.19, 8257536.0, 7665152.0)],
        [],
        dc_code="DC14",
    )
    assert out["host_count"] == 1
    row = out["hosts"][0]
    assert row["cpu_alloc_ghz"] == 0.0
    assert row["mem_alloc_gb"] == 0.0


def test_get_power_host_rows_summary_has_no_storage():
    out, _ = _run_power_rows(
        [("G2HV19DC13", 44.0, 28.65, 8388608.0, 56320.0)],
        [("G2HV19DC13", 6, 36.0, 8192000.0)],
    )
    assert out["summary"]["stor_cap_gb"] == 0.0
    assert out["storage_pools"] == []


def test_power_hosts_route_is_wired(client, mock_db):
    """A route typo would silently degrade the sellable path to 'unavailable'."""
    mock_db.get_power_host_rows.return_value = {"hosts": [], "host_count": 0}
    resp = client.get("/api/v1/datacenters/DC13/compute/power/hosts?preset=30d")
    assert resp.status_code == 200
    assert mock_db.get_power_host_rows.call_args.args[0] == "DC13"


def test_get_power_host_rows_ignores_cluster_filter():
    """Frames carry no cluster; a cluster filter must not empty the payload."""
    svc = DatabaseService()
    svc._pool = MagicMock()
    conn = MagicMock()
    svc._pool.getconn.return_value = conn
    cur = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    def fake_run_rows(cursor, query, params):
        if "ibm_lpar_general" in query:
            return [("G2HV19DC13", 6, 36.0, 8192000.0)]
        return [("G2HV19DC13", 44.0, 28.65, 8388608.0, 56320.0)]

    with patch.object(svc, "_run_rows", side_effect=fake_run_rows), patch(
        "app.services.dc_service.cache.get", return_value=None
    ), patch("app.services.dc_service.cache.run_singleflight") as mock_sf:
        mock_sf.side_effect = lambda key, factory: factory()
        out = svc.get_power_host_rows(
            "DC13", ["DC13-KM-CLS-1"], {"start": "2026-07-03", "end": "2026-08-02"}
        )
    assert out["host_count"] == 1
