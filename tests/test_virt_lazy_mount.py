"""P5: non-default Virt sub-tabs render selector + empty panel shell (heavy content deferred)."""
import ast
from pathlib import Path
from src.pages import dc_view


def _panel_children_count(stack, panel_id: str):
    found = {"node": None}

    def walk(node):
        if getattr(node, "id", None) == panel_id:
            found["node"] = node
        ch = getattr(node, "children", None)
        if isinstance(ch, (list, tuple)):
            for c in ch:
                if c is not None:
                    walk(c)
        elif ch is not None and hasattr(ch, "children"):
            walk(ch)
    for top in stack:
        if top is not None:
            walk(top)
    node = found["node"]
    assert node is not None, f"{panel_id} not found"
    ch = getattr(node, "children", None)
    if ch is None:
        return 0
    return len(ch) if isinstance(ch, (list, tuple)) else 1


_KW = dict(dc_id="DC13", classic={"hosts": 1, "cpu_cap": 10.0, "cpu_used": 5.0, "mem_cap": 10.0, "mem_used": 5.0},
           hyperconv={}, power={}, energy={}, classic_clusters=["DC13-KM-01"], hyperconv_clusters=[],
           storage_capacity={}, storage_performance={}, san_bottleneck={}, show_virt_hosts=False)


def test_shell_mode_renders_selector_but_empty_panel():
    stack = dc_view._build_virt_subtab_stack("classic", content_mode="shell", **_KW)
    assert "virt-classic-cluster-draft" in repr(stack)
    assert _panel_children_count(stack, "classic-virt-panel") == 0


def test_full_mode_renders_populated_panel():
    stack = dc_view._build_virt_subtab_stack("classic", content_mode="full", **_KW)
    assert _panel_children_count(stack, "classic-virt-panel") >= 1


def test_populate_callback_exists_with_allow_duplicate():
    src = Path("app.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "populate_virt_nested_tab":
            deco = ast.get_source_segment(src, node.decorator_list[0]) or ""
            assert "allow_duplicate=True" in deco
            assert "virt-nested-tabs" in deco
            assert "power-virt-panel" in deco
            return
    raise AssertionError("populate_virt_nested_tab callback not found")


def test_power_shell_renders_empty_panel():
    stack = dc_view._build_virt_subtab_stack("power", content_mode="shell", **_KW)
    assert _panel_children_count(stack, "power-virt-panel") == 0


def test_virt_lazy_mount_uses_shell_for_default_classic():
    from unittest.mock import patch
    from dash import html

    api_patch = {
        "get_dc_details": lambda *_a, **_k: {
            "meta": {"name": "DC13", "location": "Istanbul"},
            "classic": {"hosts": 1, "cpu_cap": 10, "cpu_used": 5, "mem_cap": 100, "mem_used": 50},
            "hyperconv": {},
            "power": {},
            "energy": {},
        },
        "get_sla_by_dc": lambda *_a, **_k: {},
        "get_classic_cluster_list": lambda *_a, **_k: ["c1"],
        "get_hyperconv_cluster_list": lambda *_a, **_k: [],
    }
    with patch.multiple("src.pages.dc_view.api", **api_patch), patch(
        "src.pages.dc_view.resolve_dc_display_from_summary",
        return_value=("DC13", "Istanbul"),
    ), patch(
        "src.pages.dc_view._build_compute_tab",
        return_value=html.Div(id="compute-stub"),
    ):
        page = dc_view.build_dc_view(
            "DC13",
            time_range={"preset": "7d"},
            eager_tabs=frozenset({"virt"}),
            virt_lazy_mount=True,
        )
    classic_panel = dc_view._find_component_by_id(page, "classic-virt-panel")
    assert classic_panel is not None
    assert classic_panel.children is None
