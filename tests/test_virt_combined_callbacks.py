"""P3: classic/hyperconv panel+sellable served by ONE combined callback (not separate)."""
import ast
from pathlib import Path


def _function_names(src_path: str) -> set[str]:
    tree = ast.parse(Path(src_path).read_text(encoding="utf-8"))
    return {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}


def _callback_outputs(func_name: str) -> list[str]:
    src = Path("app.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            deco_src = ast.get_source_segment(src, node.decorator_list[0]) or ""
            import re
            return re.findall(r'Output\(\s*"([^"]+)"', deco_src)
    raise AssertionError(f"{func_name} not found")


def test_combined_classic_callback_owns_panel_and_sellable():
    names = _function_names("app.py")
    assert "update_classic_virt_block" in names
    assert "update_classic_virt_panel" not in names
    assert "update_classic_sellable_card" not in names
    outs = _callback_outputs("update_classic_virt_block")
    assert "classic-virt-panel" in outs and "sellable-classic-card" in outs


def test_combined_hyperconv_callback_owns_panel_and_sellable():
    names = _function_names("app.py")
    assert "update_hyperconv_virt_block" in names
    assert "update_hyperconv_virt_panel" not in names
    assert "update_hyperconv_sellable_card" not in names
    outs = _callback_outputs("update_hyperconv_virt_block")
    assert "hyperconv-virt-panel" in outs and "sellable-hyperconv-card" in outs
