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
    assert "virt-classic-cluster-selector" in repr(stack)
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
            return
    raise AssertionError("populate_virt_nested_tab callback not found")
