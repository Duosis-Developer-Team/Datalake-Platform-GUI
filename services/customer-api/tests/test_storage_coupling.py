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
    assert [params[0] for _sql, params in statements] == ["virt_classic", "virt_hyperconverged"]
    assert {params[4] for _sql, params in statements} == {"arca"}


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
