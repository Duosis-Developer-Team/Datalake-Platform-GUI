"""Backup / Replication inline sellable KPI cards on DC view."""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def dc_view_module():
    if "pandas" not in sys.modules:
        sys.modules["pandas"] = types.ModuleType("pandas")
        sys.modules["pandas"].DataFrame = MagicMock()
    import importlib
    import src.pages.dc_view as dc_view
    return importlib.reload(dc_view)


def test_backup_inline_sellable_blocks_shell_mode_empty(dc_view_module):
    out = dc_view_module._backup_inline_sellable_blocks(
        "DC13",
        content_mode="shell",
        include=("backup_netbackup", "backup_veeam_replication"),
    )
    assert out == []


def test_backup_inline_sellable_blocks_calls_kpi_for_families(dc_view_module):
    calls: list[tuple] = []

    def fake_kpi(dc_id, fam, title, color="violet", selected_clusters=None, container_id=None, subtitle=None):
        calls.append((dc_id, fam, title, color, selected_clusters, container_id))
        return MagicMock(name=f"card-{fam}")

    with patch.object(dc_view_module, "_build_sellable_inline_kpi", side_effect=fake_kpi):
        out = dc_view_module._backup_inline_sellable_blocks(
            "DC13",
            classic_clusters=["c1"],
            hyperconv_clusters=["h1"],
            content_mode="full",
            include=(
                "backup_netbackup",
                "backup_veeam_replication",
                "backup_zerto_replication",
            ),
        )
    assert len(out) == 3
    fams = [c[1] for c in calls]
    assert fams == [
        "backup_netbackup",
        "backup_veeam_replication",
        "backup_zerto_replication",
    ]
    assert all(c[0] == "DC13" for c in calls)
    by_fam = {c[1]: c for c in calls}
    assert by_fam["backup_netbackup"][4] is None
    # Unified replication families: architecture filter only (no cluster lock).
    assert by_fam["backup_veeam_replication"][4] is None
    assert by_fam["backup_zerto_replication"][4] is None
    titles = [c[2] for c in calls]
    assert all(isinstance(t, str) and t for t in titles)
    assert "Potential Sales (Virtualization)" not in " ".join(titles)
    assert "Nutanix" not in " ".join(titles)
