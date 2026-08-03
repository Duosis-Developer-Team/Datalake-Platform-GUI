"""Compute/storage coupling (gui_family_storage_coupling, migration 037).

Covers the three modes an operator sets from Administration -> Platform ->
Compute / Storage:

    auto      keep the built-in pipeline behaviour
    merged    storage joins the compute min() and is capped by it
    separate  storage is sized from its own pool, never capped by CPU/RAM
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.sellable_service import SellableService, _coupling_to_triple_override
from shared.sellable.models import STORAGE_COUPLING_MODES, PanelResult, ResourceRatio, StorageCoupling


def _make_svc(couplings: list[StorageCoupling] | None = None) -> SellableService:
    svc = SellableService.__new__(SellableService)
    svc._dc_redis = None
    svc._dc_api_url = ""
    svc.list_storage_couplings = lambda: list(couplings or [])  # type: ignore[method-assign]
    svc.list_ratios = lambda: [  # type: ignore[method-assign]
        ResourceRatio(
            family="virt_intel_hana",
            cpu_per_unit=1.0,
            ram_gb_per_unit=8.0,
            storage_gb_per_unit=100.0,
        )
    ]
    svc._build_unit_lookup = lambda: {}  # type: ignore[method-assign]
    svc._get_sellable_calc_config = lambda: {  # type: ignore[method-assign]
        "effective_ghz_per_unit": 1.0,
        "physical_price_unit": "GHz",
        "power_core_to_ghz": 3.3,
    }
    return svc


def _panels(cpu: float = 10.0, ram: float = 80.0, storage: float = 5000.0) -> list[PanelResult]:
    """virt_intel_hana triple; storage is deliberately far richer than compute."""
    def _p(kind: str, raw: float, unit: str) -> PanelResult:
        return PanelResult(
            panel_key=f"virt_intel_hana_{kind}",
            label=f"HANA {kind}",
            family="virt_intel_hana",
            resource_kind=kind,
            display_unit=unit,
            total=raw * 2,
            allocated=raw,
            sellable_raw=raw,
            sellable_constrained=raw,
            unit_price_tl=1.0,
            has_price=True,
            has_infra_source=True,
        )

    return [_p("cpu", cpu, "vCPU"), _p("ram", ram, "GB"), _p("storage", storage, "GB")]


def _storage_of(panels: list[PanelResult]) -> PanelResult:
    return next(p for p in panels if p.resource_kind == "storage")


# ---------------------------------------------------------------------------
# resolution
# ---------------------------------------------------------------------------


def test_resolve_defaults_to_auto_when_no_row():
    svc = _make_svc([])
    assert svc.resolve_storage_coupling("virt_classic", "DC13") == "auto"


def test_resolve_per_dc_row_beats_global_default():
    svc = _make_svc([
        StorageCoupling(family="virt_classic", dc_code="*", mode="merged"),
        StorageCoupling(family="virt_classic", dc_code="DC13", mode="separate"),
    ])
    assert svc.resolve_storage_coupling("virt_classic", "*") == "merged"
    assert svc.resolve_storage_coupling("virt_classic", "DC13") == "separate"
    # A DC without its own row falls back to the '*' row.
    assert svc.resolve_storage_coupling("virt_classic", "DC14") == "merged"


def test_resolve_rejects_garbage_mode():
    svc = _make_svc([StorageCoupling(family="virt_classic", dc_code="*", mode="nonsense")])
    assert svc.resolve_storage_coupling("virt_classic", "*") == "auto"


def test_list_storage_couplings_survives_missing_table():
    """Older DBs without migration 037 must keep the built-in behaviour."""
    svc = SellableService.__new__(SellableService)
    webui = MagicMock()
    webui.is_available = True
    webui.run_rows.side_effect = RuntimeError('relation "gui_family_storage_coupling" does not exist')
    svc._webui = webui
    assert svc.list_storage_couplings() == []


def test_list_storage_couplings_without_webui_attribute():
    svc = SellableService.__new__(SellableService)
    assert svc.list_storage_couplings() == []


def test_coupling_to_triple_override():
    assert _coupling_to_triple_override("merged") is True
    assert _coupling_to_triple_override("separate") is False
    assert _coupling_to_triple_override("auto") is None
    assert set(STORAGE_COUPLING_MODES) == {"auto", "merged", "separate"}


# ---------------------------------------------------------------------------
# effect on the numbers
# ---------------------------------------------------------------------------


def test_auto_is_a_no_op_versus_no_row_at_all():
    """Seeding every family as 'auto' must not move a single number."""
    baseline = _make_svc([])._apply_family_constraints_to_results(_panels(), "DC13")
    seeded = _make_svc([
        StorageCoupling(family="virt_intel_hana", dc_code="*", mode="auto"),
    ])._apply_family_constraints_to_results(_panels(), "DC13")

    assert [p.sellable_constrained for p in baseline] == [p.sellable_constrained for p in seeded]


def test_separate_keeps_storage_off_the_compute_bottleneck():
    merged = _make_svc([
        StorageCoupling(family="virt_intel_hana", dc_code="*", mode="merged"),
    ])._apply_family_constraints_to_results(_panels(), "DC13")
    separate = _make_svc([
        StorageCoupling(family="virt_intel_hana", dc_code="*", mode="separate"),
    ])._apply_family_constraints_to_results(_panels(), "DC13")

    # n = min(cpu 10/1, ram 80/8, storage 5000/100) = 10 -> merged caps storage at 1000 GB.
    assert _storage_of(merged).sellable_constrained == pytest.approx(1000.0)
    # separate leaves the raw storage pool alone.
    assert _storage_of(separate).sellable_constrained == pytest.approx(5000.0)
    assert _storage_of(separate).sellable_constrained > _storage_of(merged).sellable_constrained


def test_compute_is_unchanged_by_the_coupling_mode():
    """The rule is about storage; CPU/RAM must be identical in both modes."""
    merged = _make_svc([
        StorageCoupling(family="virt_intel_hana", dc_code="*", mode="merged"),
    ])._apply_family_constraints_to_results(_panels(), "DC13")
    separate = _make_svc([
        StorageCoupling(family="virt_intel_hana", dc_code="*", mode="separate"),
    ])._apply_family_constraints_to_results(_panels(), "DC13")

    def _compute(panels: list[PanelResult]) -> dict[str, float]:
        return {p.resource_kind: p.sellable_constrained for p in panels if p.resource_kind != "storage"}

    assert _compute(merged) == _compute(separate)


def test_operator_setting_is_traceable_in_the_panel_notes():
    out = _make_svc([
        StorageCoupling(family="virt_intel_hana", dc_code="*", mode="separate"),
    ])._apply_family_constraints_to_results(_panels(), "DC13")
    notes = " ".join(_storage_of(out).notes)
    assert "storage coupling" in notes
    assert "operator setting" in notes


def test_auto_leaves_no_operator_note():
    out = _make_svc([
        StorageCoupling(family="virt_intel_hana", dc_code="*", mode="auto"),
    ])._apply_family_constraints_to_results(_panels(), "DC13")
    assert not any("storage coupling" in n for n in _storage_of(out).notes)


def test_per_dc_override_only_moves_that_dc():
    couplings = [
        StorageCoupling(family="virt_intel_hana", dc_code="*", mode="merged"),
        StorageCoupling(family="virt_intel_hana", dc_code="DC14", mode="separate"),
    ]
    dc13 = _make_svc(couplings)._apply_family_constraints_to_results(_panels(), "DC13")
    dc14 = _make_svc(couplings)._apply_family_constraints_to_results(_panels(), "DC14")

    assert _storage_of(dc13).sellable_constrained == pytest.approx(1000.0)
    assert _storage_of(dc14).sellable_constrained == pytest.approx(5000.0)


# ---------------------------------------------------------------------------
# writes
# ---------------------------------------------------------------------------


def test_upsert_rejects_invalid_mode():
    svc = SellableService.__new__(SellableService)
    svc._webui = MagicMock(is_available=True)
    with pytest.raises(ValueError):
        svc.upsert_storage_coupling("virt_classic", mode="sometimes")


def test_bulk_upsert_is_one_transaction():
    svc = SellableService.__new__(SellableService)
    webui = MagicMock()
    webui.is_available = True
    svc._webui = webui

    saved = svc.upsert_storage_couplings(
        [
            {"family": "virt_classic", "dc_code": "*", "mode": "separate"},
            {"family": "virt_hyperconverged", "dc_code": "*", "mode": "merged"},
        ],
        updated_by="arca",
    )

    assert saved == 2
    webui.execute_all.assert_called_once()
    statements = webui.execute_all.call_args[0][0]
    # (family, dc_code, scope_kind, scope_key, mode, notes, updated_by)
    assert [params[0] for _sql, params in statements] == ["virt_classic", "virt_hyperconverged"]
    assert {params[2] for _sql, params in statements} == {"family"}
    assert {params[3] for _sql, params in statements} == {""}
    assert [params[4] for _sql, params in statements] == ["separate", "merged"]
    assert {params[6] for _sql, params in statements} == {"arca"}


def test_upsert_never_sends_a_bare_null_into_the_not_null_notes_column():
    """Postgres builds the proposed row before ON CONFLICT, so a NULL note is a 500.

    The board saves modes without touching notes, i.e. it always sends None.
    """
    from pathlib import Path

    import app.db.queries.sellable as sq

    migration = (
        Path(__file__).resolve().parents[1] / "migrations" / "webui" / "037_family_storage_coupling.sql"
    ).read_text(encoding="utf-8")
    notes_col = next(line for line in migration.splitlines() if line.strip().startswith("notes"))
    assert "NOT NULL" in notes_col

    insert_values = sq.UPSERT_STORAGE_COUPLING.split("ON CONFLICT")[0]
    assert "COALESCE(%s,'')" in insert_values
    # ...and an empty note must not wipe the seeded explanation on update.
    assert "NULLIF(EXCLUDED.notes, '')" in sq.UPSERT_STORAGE_COUPLING


def test_bulk_upsert_rejects_the_whole_board_on_a_bad_row():
    svc = SellableService.__new__(SellableService)
    webui = MagicMock()
    webui.is_available = True
    svc._webui = webui

    with pytest.raises(ValueError):
        svc.upsert_storage_couplings([
            {"family": "virt_classic", "dc_code": "*", "mode": "separate"},
            {"family": "virt_power", "dc_code": "*", "mode": "merged-ish"},
        ])
    webui.execute_all.assert_not_called()


# ---------------------------------------------------------------------------
# cluster scope (migration 038)
# ---------------------------------------------------------------------------


def _host(name: str, cluster: str, *, pooled: bool) -> dict:
    """One compute-API host row, with the fields the coupling path reads."""
    return {
        "host": name,
        "cluster": cluster,
        "cpu_cap": 100.0,
        "mem_cap": 800.0,
        "stor_cap_gb": 50_000.0,
        "storage_cluster_pool": pooled,
    }


def test_cluster_row_beats_family_row_in_the_same_dc():
    svc = _make_svc([
        StorageCoupling(family="virt_classic", dc_code="*", mode="merged"),
        StorageCoupling(family="virt_classic", dc_code="DC13", mode="merged"),
        StorageCoupling(
            family="virt_classic", dc_code="DC13", mode="separate",
            scope_kind="cluster", scope_key="DC13-KM-CLS-NVME",
        ),
    ])
    assert svc.resolve_storage_coupling(
        "virt_classic", "DC13", cluster="DC13-KM-CLS-NVME",
    ) == "separate"
    # A sibling cluster with no row of its own still follows the family.
    assert svc.resolve_storage_coupling(
        "virt_classic", "DC13", cluster="DC13-KM2-CLS-NVME",
    ) == "merged"


def test_cluster_rows_are_scoped_to_their_own_dc():
    """Cluster names are DC-local; a DC13 rule must not leak into DC14."""
    svc = _make_svc([
        StorageCoupling(
            family="virt_classic", dc_code="DC13", mode="separate",
            scope_kind="cluster", scope_key="SHARED-NAME",
        ),
    ])
    assert svc.resolve_storage_coupling("virt_classic", "DC14", cluster="SHARED-NAME") == "auto"


def test_resolver_is_a_plain_value_when_no_cluster_rows_exist():
    """The common case must not pay for a per-host callable."""
    svc = _make_svc([StorageCoupling(family="virt_classic", dc_code="DC13", mode="merged")])
    lookup = svc._build_coupling_lookup()
    assert svc.build_host_coupling_resolver("virt_classic", "DC13", lookup) is True


def test_resolver_decides_per_host_when_a_cluster_row_exists():
    svc = _make_svc([
        StorageCoupling(family="virt_classic", dc_code="DC13", mode="merged"),
        StorageCoupling(
            family="virt_classic", dc_code="DC13", mode="separate",
            scope_kind="cluster", scope_key="DC13-KM-CLS-NVME",
        ),
    ])
    resolve = svc.build_host_coupling_resolver(
        "virt_classic", "DC13", svc._build_coupling_lookup(),
    )
    assert callable(resolve)
    assert resolve(_host("esx01", "DC13-KM-CLS-NVME", pooled=False)) is False
    assert resolve(_host("esx09", "DC13-KM2-CLS-NVME", pooled=False)) is True


def test_resolver_falls_back_to_auto_for_untouched_clusters_when_family_is_auto():
    """An override on one cluster must not drag its siblings out of 'auto'."""
    svc = _make_svc([
        StorageCoupling(
            family="virt_hyperconverged", dc_code="DC13", mode="merged",
            scope_kind="cluster", scope_key="DC13-G12-SSD",
        ),
    ])
    resolve = svc.build_host_coupling_resolver(
        "virt_hyperconverged", "DC13", svc._build_coupling_lookup(),
    )
    assert resolve(_host("ntx01", "DC13-G12-SSD", pooled=True)) is True
    # None = "keep host_storage_in_triple deciding", i.e. the built-in rule.
    assert resolve(_host("ntx09", "DC13-G14-HYBRID", pooled=True)) is None


def test_callable_override_reaches_only_its_own_cluster():
    """End-to-end through the computation layer, not just the resolver."""
    from shared.sellable.computation import constrain_by_ratio_per_host_triple_dual

    ratio = ResourceRatio(
        family="virt_classic", cpu_per_unit=1.0, ram_gb_per_unit=8.0,
        storage_gb_per_unit=100.0,
    )
    hosts = [
        _host("a1", "CLS-A", pooled=True),
        _host("b1", "CLS-B", pooled=True),
    ]
    seen: list[str] = []

    def override(host: dict) -> bool | None:
        seen.append(str(host.get("cluster")))
        return True if host.get("cluster") == "CLS-A" else None

    constrain_by_ratio_per_host_triple_dual(
        _panels(), ratio, hosts, storage_in_triple_override=override,
    )
    assert set(seen) == {"CLS-A", "CLS-B"}


def test_cluster_scope_requires_a_concrete_dc_and_a_name():
    svc = SellableService.__new__(SellableService)
    webui = MagicMock()
    webui.is_available = True
    svc._webui = webui

    with pytest.raises(ValueError):
        # cluster scope without a cluster name
        svc.upsert_storage_coupling(
            "virt_classic", dc_code="DC13", mode="merged", scope_kind="cluster",
        )
    with pytest.raises(ValueError):
        # cluster names are DC-local, so '*' would apply to every DC
        svc.upsert_storage_coupling(
            "virt_classic", dc_code="*", mode="merged",
            scope_kind="cluster", scope_key="DC13-KM-CLS-NVME",
        )
    with pytest.raises(ValueError):
        svc.upsert_storage_coupling("virt_classic", scope_kind="rack")
    webui.execute.assert_not_called()


def test_family_scope_never_carries_a_key():
    """Two spellings of the family default would make resolution arbitrary."""
    svc = SellableService.__new__(SellableService)
    webui = MagicMock()
    webui.is_available = True
    svc._webui = webui

    svc.upsert_storage_coupling(
        "virt_classic", dc_code="DC13", mode="merged",
        scope_kind="family", scope_key="leftover-from-the-ui",
    )
    params = webui.execute.call_args[0][1]
    assert params[2] == "family"
    assert params[3] == ""


def test_delete_keeps_the_global_family_default():
    """The '*' family row is the last fallback before 'auto'."""
    import app.db.queries.sellable as sq

    assert "NOT (dc_code = '*' AND scope_kind = 'family')" in sq.DELETE_STORAGE_COUPLING


def test_pre_038_rows_are_read_as_family_scoped():
    """An un-migrated DB has neither column and must still resolve."""
    svc = SellableService.__new__(SellableService)
    webui = MagicMock()
    webui.is_available = True
    webui.run_rows.return_value = [
        {"family": "virt_classic", "dc_code": "*", "mode": "merged"},
    ]
    svc._webui = webui
    (row,) = svc.list_storage_couplings()
    assert (row.scope_kind, row.scope_key) == ("family", "")
    assert svc.resolve_storage_coupling("virt_classic", "DC13") == "merged"


# ---------------------------------------------------------------------------
# Replication Classic/HC — independent ratios; coupling default separate
# ---------------------------------------------------------------------------


def _repl_panels(
    cpu: float = 10.0, ram: float = 40.0, storage: float = 5000.0,
) -> list[PanelResult]:
    """backup_veeam_replication_classic at seed ratio 1:4:50."""

    def _p(kind: str, raw: float, unit: str) -> PanelResult:
        return PanelResult(
            panel_key=f"backup_veeam_replication_classic_{kind}",
            label=f"Veeam Classic {kind}",
            family="backup_veeam_replication_classic",
            resource_kind=kind,
            display_unit=unit,
            total=raw * 2,
            allocated=raw,
            sellable_raw=raw,
            sellable_constrained=raw,
            unit_price_tl=1.0,
            has_price=True,
            has_infra_source=True,
        )

    return [_p("cpu", cpu, "vCPU"), _p("ram", ram, "GB"), _p("storage", storage, "GB")]


def _make_repl_svc(mode: str) -> SellableService:
    """Host-based replication without host rows → fallback + family coupling."""
    from shared.sellable.computation import constrain_by_ratio

    fam = "backup_veeam_replication_classic"
    svc = SellableService.__new__(SellableService)
    svc._dc_redis = None
    svc._dc_api_url = ""
    svc.list_storage_couplings = lambda: [  # type: ignore[method-assign]
        StorageCoupling(family=fam, dc_code="*", mode=mode),
    ]
    svc.list_ratios = lambda: [  # type: ignore[method-assign]
        ResourceRatio(
            family=fam,
            cpu_per_unit=1.0,
            ram_gb_per_unit=4.0,
            storage_gb_per_unit=50.0,
        )
    ]
    svc._build_unit_lookup = lambda: {}  # type: ignore[method-assign]
    svc._get_sellable_calc_config = lambda: {  # type: ignore[method-assign]
        "effective_ghz_per_unit": 1.0,
        "physical_price_unit": "GHz",
        "power_core_to_ghz": 3.3,
    }
    svc._fetch_host_rows = lambda *a, **k: ([], "unavailable", [])  # type: ignore[method-assign]

    def _fallback(group, ratio, *a, **k):
        compute = [p for p in group if (p.resource_kind or "").lower() != "storage"]
        storage = [p for p in group if (p.resource_kind or "").lower() == "storage"]
        out = constrain_by_ratio(compute, ratio, decouple_resource_kinds=None) if compute else []
        for sto in storage:
            sto.sellable_constrained = float(sto.sellable_raw or 0.0)
            sto.ratio_bound = False
            out.append(sto)
        return out

    svc._apply_cluster_fallback_dual = _fallback  # type: ignore[method-assign]
    return svc


def test_replication_separate_matches_auto_storage_uncapped():
    """Seed default 'separate' keeps dedicated DS pool (status quo)."""
    separate = _make_repl_svc("separate")._apply_family_constraints_to_results(
        _repl_panels(), "DC13",
    )
    auto = _make_repl_svc("auto")._apply_family_constraints_to_results(
        _repl_panels(), "DC13",
    )
    assert _storage_of(separate).sellable_constrained == pytest.approx(5000.0)
    assert _storage_of(auto).sellable_constrained == pytest.approx(5000.0)


def test_replication_merged_caps_storage_by_compute_ratio():
    """Operator merged on Compute / Storage must override the hard skip."""
    merged = _make_repl_svc("merged")._apply_family_constraints_to_results(
        _repl_panels(), "DC13",
    )
    # n = min(10/1, 40/4) = 10 → storage cap 10 * 50 = 500 GB
    assert _storage_of(merged).sellable_constrained == pytest.approx(500.0)
    notes = " ".join(_storage_of(merged).notes)
    assert "storage coupling" in notes
    assert "merged" in notes


def test_replication_merged_dual_track_storage_mirrors_avg_when_alloc_zero():
    """When Alloc/Max are gated to 0 but Ort has packages, storage Ort follows ratio."""
    from shared.sellable.computation import apply_storage_dual_track_ratio_caps

    fam = "backup_veeam_replication_classic"
    panels = _repl_panels(cpu=10.0, ram=40.0, storage=50000.0)
    for p in panels:
        if p.resource_kind == "cpu":
            p.sellable_allocation = 0.0
            p.sellable_max_util = 0.0
            p.sellable_avg_util = 141.0
            p.sellable_constrained = 0.0
        elif p.resource_kind == "ram":
            p.sellable_allocation = 0.0
            p.sellable_max_util = 0.0
            p.sellable_avg_util = 564.0
            p.sellable_constrained = 0.0
        else:
            p.sellable_raw = 50000.0
            p.sellable_constrained = 0.0
    ratio = ResourceRatio(
        family=fam, cpu_per_unit=1.0, ram_gb_per_unit=4.0, storage_gb_per_unit=50.0,
    )
    out = apply_storage_dual_track_ratio_caps(panels, ratio)
    sto = _storage_of(out)
    assert sto.sellable_allocation == pytest.approx(0.0)
    assert sto.sellable_avg_util == pytest.approx(7050.0)
