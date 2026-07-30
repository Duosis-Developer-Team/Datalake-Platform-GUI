"""Layout smoke tests for Platform Backup Mapping settings.

Pure build_layout checks — no Dash server required.
"""
from __future__ import annotations

from dash import dash_table, html
import dash_mantine_components as dmc

from src.pages.settings.platform import backup_mapping
from src.pages.settings.integrations import crm_backup


def _walk(node, predicate):
    if predicate(node):
        yield node
    children = getattr(node, "children", None)
    if children is None:
        return
    if not isinstance(children, (list, tuple)):
        children = [children]
    for child in children:
        yield from _walk(child, predicate)


def _find_datatables(layout) -> list[dash_table.DataTable]:
    return list(_walk(layout, lambda n: isinstance(n, dash_table.DataTable)))


def _find_multiselects(layout) -> list:
    return list(_walk(layout, lambda n: isinstance(n, dmc.MultiSelect)))


def test_backup_mapping_layout_is_div():
    layout = backup_mapping.build_layout()
    assert isinstance(layout, html.Div)


def test_backup_mapping_seeds_policy_multiselects_from_yaml():
    layout = backup_mapping.build_layout()
    selects = {ms.id: ms for ms in _find_multiselects(layout) if getattr(ms, "id", None)}
    assert "pbm-image-policy-types" in selects
    assert "pbm-application-policy-types" in selects
    image = selects["pbm-image-policy-types"]
    assert "VMWARE" in (image.value or [])
    app = selects["pbm-application-policy-types"]
    assert "SAP" in (app.value or [])
    assert "SQL_SERVER" in (app.value or [])


def test_backup_mapping_replica_tables_seeded():
    layout = backup_mapping.build_layout()
    tables = {t.id: t for t in _find_datatables(layout) if getattr(t, "id", None)}
    assert backup_mapping._VEEAM_TABLE_ID in tables
    assert backup_mapping._ZERTO_TABLE_ID in tables
    veeam = tables[backup_mapping._VEEAM_TABLE_ID]
    assert len(veeam.data) >= 1
    ids = {row["id"] for row in veeam.data}
    assert "suffix_dr" in ids
    assert veeam.filter_action == "native"


def test_backup_mapping_multipliers_table_present():
    layout = backup_mapping.build_layout()
    tables = {t.id: t for t in _find_datatables(layout) if getattr(t, "id", None)}
    assert backup_mapping._SNAPSHOT_TABLE_ID in tables
    assert tables[backup_mapping._SNAPSHOT_TABLE_ID].data == []


def test_crm_backup_reexports_platform_layout():
    """Soft-deprecated CRM Backup module must re-export Platform build_layout."""
    assert crm_backup.build_layout is backup_mapping.build_layout
    layout = crm_backup.build_layout()
    assert isinstance(layout, html.Div)
