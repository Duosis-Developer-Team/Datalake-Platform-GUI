"""virt_power on the host-based sellable path.

An IBM frame bounds its partitions the way a hypervisor host bounds its VMs, so
Power CPU/RAM are computed frame by frame. Two things make Power different from
the other host-based families and are what these tests pin down:

  * its rows report **cores**, not GHz, so no CPU unit conversion may creep in;
  * its **storage** panel stays on the aggregate branch -- the arrays behind the
    frames also serve the classic estate, so free space is not attributable per
    frame -- and reaches the compute bottleneck through apply_storage_ratio_cap
    instead of the per-host min().
"""
from __future__ import annotations

from unittest.mock import MagicMock

from app.services.sellable_service import (
    SellableService,
    _CLUSTERLESS_HOST_ROW_FAMILIES,
    _FAMILY_COMPUTE_ENDPOINT,
    _FAMILY_HOST_CPU_UNIT,
    _HOST_BASED_FAMILIES,
    _HOST_COMPUTE_ONLY_FAMILIES,
)
from shared.sellable.models import (
    InfraSource,
    PanelDefinition,
    ResourceRatio,
)


POWER_PANELS = [
    PanelDefinition("virt_power_cpu",     "Power CPU",     "virt_power", "cpu",     "Core"),
    PanelDefinition("virt_power_ram",     "Power RAM",     "virt_power", "ram",     "GB"),
    PanelDefinition("virt_power_storage", "Power Storage", "virt_power", "storage", "GB"),
]

# Aggregate totals as the DC payload reports them. CPU/RAM are allocated 85%,
# i.e. over the 80% threshold: on the aggregate path the DC-wide gate zeroes
# the whole family. This is the real DC11/DC13/DC15 shape.
POWER_INFRA = {
    "virt_power_cpu": (
        InfraSource("virt_power_cpu", "*", "ibm_server_general", "totalprocunits", "Core"),
        (200.0, 170.0),
    ),
    "virt_power_ram": (
        InfraSource("virt_power_ram", "*", "ibm_server_general", "totalmem", "GB"),
        (2000.0, 1700.0),
    ),
    "virt_power_storage": (
        InfraSource("virt_power_storage", "*", "ibm_storage_pools", "total_gb", "GB"),
        (10000.0, 4000.0),
    ),
}

# 1 Core + 16 GB + 200 GB storage per unit — the live virt_power ratio.
POWER_RATIO = ResourceRatio(
    family="virt_power", cpu_per_unit=1.0, ram_gb_per_unit=16.0, storage_gb_per_unit=200.0
)

RANGE_INPUTS = {
    "intel_cap_gb": 1000.0,
    "intel_used_gb": 100.0,
    "ibm_ds_cap_gb": 2000.0,
    "ibm_ds_used_gb": 200.0,
    "ibm_total_gb": 10000.0,
    "ibm_used_gb": 4000.0,
    "ibm_physical_free_gb": 5000.0,
}


def _frame(name: str, cpu_cap: float, cpu_alloc: float, mem_cap: float, mem_alloc: float) -> dict:
    """A row shaped like /compute/power/hosts emits it (cores, no storage)."""
    cpu_pct = 100.0 * cpu_alloc / cpu_cap if cpu_cap else 0.0
    mem_pct = 100.0 * mem_alloc / mem_cap if mem_cap else 0.0
    return {
        "host": name,
        "cluster": "",
        "vm_count": 4,
        "cpu_cap_ghz": cpu_cap,          # carries CORES for Power
        "cpu_alloc_ghz": cpu_alloc,
        "cpu_alloc_ghz_physical": cpu_alloc,
        "cpu_used_ghz": cpu_cap * 0.4,
        "cpu_used_ghz_peak": cpu_cap * 0.4,
        "cpu_used_pct": 40.0,
        "cpu_peak_util_pct": 40.0,
        "ghz_per_core": 1.0,
        "cpu_cap_cores": cpu_cap,
        "mem_cap_gb": mem_cap,
        "mem_alloc_gb": mem_alloc,
        "mem_used_gb": mem_cap * mem_pct / 100.0,
        "mem_used_gb_peak": mem_cap * mem_pct / 100.0,
        "mem_cap_gb_at_peak": mem_cap,
        "mem_used_pct": mem_pct,
        "mem_peak_util_pct": mem_pct,
        "mem_alloc_pct": mem_pct,
        "cpu_alloc_pct": cpu_pct,
        "stor_cap_gb": 0.0,
        "stor_provisioned_gb": 0.0,
        "stor_used_gb": 0.0,
        "stor_used_pct": 0.0,
        "km_shared_storage": True,
    }


# Frame A is over the threshold on both axes and sells nothing.
# Frame B is at 75% on both: cpu headroom 100*0.80-75 = 5 cores,
# ram headroom 1000*0.80-750 = 50 GB -> min(5/1, 50/16) = 3.125 units.
FRAME_BLOCKED = _frame("G2HV1DC13", 100.0, 95.0, 1000.0, 950.0)
FRAME_FREE = _frame("G2HV2DC13", 100.0, 75.0, 1000.0, 750.0)


def _build_power_service(host_rows: list[dict] | None, *, range_inputs: dict | None = RANGE_INPUTS):
    customer = MagicMock()
    customer._pool = MagicMock()
    webui = MagicMock()
    webui.is_available = False  # keep _get_sellable_calc_config on its defaults

    svc = SellableService(
        customer_service=customer,
        webui=webui,
        config_service=MagicMock(),
        currency_service=MagicMock(),
        tagging_service=MagicMock(),
        datacenter_api_url="http://dc-api:8000",
    )
    svc.list_panel_defs = lambda: POWER_PANELS
    svc.list_unit_conversions = lambda: []  # no Core->Core row exists in prod either
    svc.list_ratios = lambda: [POWER_RATIO]
    svc.list_storage_couplings = lambda: []
    svc.get_threshold = lambda panel_key, kind, dc: 85.0 if kind == "storage" else 80.0
    svc.get_unit_price_tl = lambda panel_key: (10.0, True)
    svc.get_infra_source = lambda panel_key, dc="*": POWER_INFRA[panel_key][0]
    svc._query_total_allocated = lambda src, dc: POWER_INFRA[src.panel_key][1]
    svc._query_storage_range_inputs = lambda dc: range_inputs
    svc._compute_ytd_sales_tl = lambda: 0.0
    svc._count_unmapped_products = lambda: 0
    svc._fetch_host_rows = lambda dc, fam, clusters: (
        (host_rows, "ok", []) if host_rows else (None, "unavailable", [])
    )
    svc._fetch_compute_response = lambda *a, **kw: None
    return svc


def _panels(svc, **kw):
    return {
        p.resource_kind: p
        for p in svc.compute_all_panels(dc_code="DC13", family="virt_power", **kw)
    }


# --------------------------------------------------------------- wiring/config


def test_virt_power_resolves_to_the_power_compute_endpoint():
    assert _FAMILY_COMPUTE_ENDPOINT["virt_power"] == "power"


def test_virt_power_is_host_based_but_compute_only_and_clusterless():
    assert "virt_power" in _HOST_BASED_FAMILIES
    assert "virt_power" in _HOST_COMPUTE_ONLY_FAMILIES
    assert "virt_power" in _CLUSTERLESS_HOST_ROW_FAMILIES
    assert _FAMILY_HOST_CPU_UNIT["virt_power"] == "Core"
    # The hypervisor families must not have picked up Power's exceptions.
    assert _HOST_COMPUTE_ONLY_FAMILIES.isdisjoint({"virt_classic", "virt_hyperconverged"})
    assert _CLUSTERLESS_HOST_ROW_FAMILIES.isdisjoint({"virt_classic", "virt_hyperconverged"})


def test_fetch_host_rows_hits_the_power_hosts_url(monkeypatch):
    svc = _build_power_service(None)
    seen: list[str] = []
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"hosts": [FRAME_FREE], "storage_pools": []}

    def fake_get(url, *a, **kw):
        seen.append(url)
        return resp

    monkeypatch.setattr("app.services.sellable_service.httpx.get", fake_get)
    hosts, status, _pools = SellableService._fetch_host_rows(svc, "DC13", "virt_power", None)

    assert status == "ok"
    assert len(hosts) == 1
    assert seen[0].startswith("http://dc-api:8000/api/v1/datacenters/DC13/compute/power/hosts")


def test_cluster_filter_is_not_forwarded_for_power():
    """Frames carry no cluster; forwarding the filter would empty the payload
    and silently drop the family to the cluster fallback."""
    svc = _build_power_service([FRAME_FREE])
    seen: list[tuple] = []

    def spy(dc, fam, clusters):
        seen.append((dc, fam, clusters))
        return [FRAME_FREE], "ok", []

    svc._fetch_host_rows = spy
    svc.compute_all_panels(dc_code="DC13", family="virt_power", selected_clusters=["KM-1"])

    assert seen == [("DC13", "virt_power", None)]


def test_host_cpu_unit_core_is_passed_to_the_constraint_step():
    """GHz would send the panel through a divide-by-8 conversion it must not have."""
    svc = _build_power_service([FRAME_FREE])
    seen: dict = {}
    real = svc._apply_host_based_constraints

    def spy(*args, **kwargs):
        seen.update(kwargs)
        return real(*args, **kwargs)

    svc._apply_host_based_constraints = spy
    svc.compute_all_panels(dc_code="DC13", family="virt_power")

    assert seen["host_cpu_unit"] == "Core"
    assert seen["family"] == "virt_power"


# ------------------------------------------------------------ compute per frame


def test_power_cpu_ram_are_summed_frame_by_frame():
    svc = _build_power_service([FRAME_BLOCKED, FRAME_FREE])
    p = _panels(svc)

    # Only the free frame contributes: 5 cores / 50 GB of gated headroom.
    assert p["cpu"].total == 200.0
    assert p["cpu"].allocated == 170.0
    assert p["cpu"].sellable_raw == 5.0
    assert p["ram"].sellable_raw == 50.0
    # min(5/1, 50/16) = 3.125 units on the free frame, 0 on the blocked one.
    assert p["cpu"].sellable_constrained == 3.125
    assert p["ram"].sellable_constrained == 50.0
    assert p["cpu"].computation_mode == "power_allocation_only"


def test_power_host_based_survives_a_dc_wide_gate_that_would_zero_it():
    """DC-wide allocation is 85% > 80%: the aggregate path gates the family to
    zero. Frame-level evaluation keeps the frames that are actually under."""
    svc = _build_power_service([FRAME_BLOCKED, FRAME_FREE])
    host_based = _panels(svc)

    aggregate = _panels(_build_power_service(None))

    assert aggregate["cpu"].sellable_constrained == 0.0
    assert aggregate["cpu"].gate_blocked is True
    assert host_based["cpu"].sellable_constrained > 0.0
    assert host_based["cpu"].gate_blocked is False


def test_power_cpu_stays_in_cores_with_no_conversion():
    """cpu_cap_ghz carries cores; a GHz->Core divide would shrink it 8x."""
    svc = _build_power_service([FRAME_FREE])
    p = _panels(svc)
    assert p["cpu"].display_unit == "Core"
    assert p["cpu"].total == 100.0  # the frame's own core capacity, verbatim
    assert p["cpu"].allocated == 75.0


def test_power_frames_report_no_storage_and_it_stays_out_of_the_host_min():
    """stor_cap_gb=0 must not drag the per-frame min() to zero."""
    svc = _build_power_service([FRAME_FREE])
    p = _panels(svc)
    assert p["cpu"].sellable_constrained == 3.125


# ------------------------------------------------------------- storage handling


def test_power_storage_keeps_its_aggregate_range_not_the_frames_zeros():
    """The host path must not overwrite the storage panel with per-frame zeros."""
    svc = _build_power_service([FRAME_BLOCKED, FRAME_FREE])
    sto = _panels(svc)["storage"]

    assert sto.total == RANGE_INPUTS["ibm_total_gb"]        # 10 000, not 0
    assert sto.allocated == 3800.0                          # ibm_used - KM-exposed
    assert sto.sellable_min is not None and sto.sellable_max is not None
    assert any("Power storage range" in n for n in sto.notes)


def test_power_storage_is_capped_by_the_host_based_compute_bottleneck():
    """Storage leaves the per-frame min() but must still not exceed what the
    frames can actually run: 3.125 units x 200 GB = 625 GB."""
    svc = _build_power_service([FRAME_BLOCKED, FRAME_FREE])
    sto = _panels(svc)["storage"]

    assert sto.sellable_constrained == 625.0
    assert sto.sellable_max == 625.0
    assert sto.ratio_bound is True
    assert sto.bottleneck_units == 3.125


def test_power_storage_range_is_skipped_when_datalake_inputs_are_missing():
    svc = _build_power_service([FRAME_FREE], range_inputs=None)
    sto = _panels(svc)["storage"]
    assert any("storage range skipped" in n for n in sto.notes)


def test_power_storage_without_host_rows_matches_the_aggregate_path():
    """Removing the frames must leave the storage panel exactly as it was --
    the deferral is the only thing the host path does to it."""
    with_hosts = _panels(_build_power_service([FRAME_BLOCKED, FRAME_FREE]))["storage"]
    without = _panels(_build_power_service(None))["storage"]

    assert with_hosts.total == without.total
    assert with_hosts.allocated == without.allocated
    # The aggregate path's compute is gate-blocked, so its storage caps to 0;
    # the host path leaves 3.125 units of compute to carry storage.
    assert without.sellable_constrained == 0.0
    assert with_hosts.sellable_constrained == 625.0


# ------------------------------------------------------------ global inventory


def test_power_storage_survives_the_global_merge_that_zeroes_sellable_raw():
    """Global inventory re-runs the family pipeline on pre-merged panels whose
    sellable_raw has been reset to 0. The deferred storage panel has to be
    rebuilt from the merged totals, or it caps down from zero while CPU/RAM --
    recomputed from the frames -- report real numbers."""
    from app.services.inventory_overview_service import _merge_panel_results

    svc = _build_power_service([FRAME_BLOCKED, FRAME_FREE])
    svc._fetch_host_rows_multi = lambda dcs, fam, clusters, **kw: (
        [FRAME_BLOCKED, FRAME_FREE], "ok", []
    )
    merged = [_merge_panel_results(None, p) for p in _panels(svc).values()]
    assert all(p.sellable_raw == 0.0 for p in merged)  # what the merge hands us

    out = {
        p.resource_kind: p
        for p in svc.recompute_family_constraints(
            merged, dc_code="*", infra_dc_codes=["DC13"],
        )
    }

    assert out["cpu"].sellable_constrained == 3.125
    # Rebuilt from the merged totals -- 10 000 x 85% minus the 3 800 the per-DC
    # pass already netted of KM-exposed capacity -- then capped by the frames'
    # 3.125 units x 200 GB.
    assert out["storage"].sellable_raw == 4700.0
    assert out["storage"].sellable_constrained == 625.0
