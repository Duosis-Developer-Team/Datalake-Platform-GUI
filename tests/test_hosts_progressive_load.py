"""Progressive host loading: virt block decoupled from hosts; prefetch + collapse render."""
import ast
import re
from pathlib import Path


def _function_source(func_name: str) -> str:
    src = Path("app.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            return ast.get_source_segment(src, node) or ""
    raise AssertionError(f"{func_name} not found")


def _callback_outputs(func_name: str) -> list[str]:
    src = Path("app.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            deco_src = ast.get_source_segment(src, node.decorator_list[0]) or ""
            return re.findall(r'Output\(\s*"([^"]+)"', deco_src)
    raise AssertionError(f"{func_name} not found")


def test_virt_block_callbacks_do_not_fetch_hosts():
    for fn in ("update_classic_virt_block", "update_hyperconv_virt_block"):
        body = _function_source(fn)
        assert "get_classic_host_rows" not in body and "get_hyperconv_host_rows" not in body
        assert '"hosts"' not in body


def test_virt_block_owns_panel_and_sellable_only():
    for fn in ("update_classic_virt_block", "update_hyperconv_virt_block"):
        outs = _callback_outputs(fn)
        assert len(outs) == 2
        assert "hosts-panel" not in "".join(outs)
        assert "hosts-count" not in "".join(outs)


def test_prefetch_callbacks_exist():
    names = {n.name for n in ast.walk(ast.parse(Path("app.py").read_text())) if isinstance(n, ast.FunctionDef)}
    assert "prefetch_classic_hosts" in names
    assert "prefetch_hyperconv_hosts" in names


def test_render_callbacks_fire_on_collapse_and_store():
    for fn in ("render_classic_hosts_panel", "render_hyperconv_hosts_panel"):
        deco = Path("app.py").read_text(encoding="utf-8")
        assert f"def {fn}" in deco
        outs = _callback_outputs(fn)
        assert any("hosts-panel" in o for o in outs)
        body = _function_source(fn)
        assert "collapsed_in" in body
        assert "_build_hosts_panel_content" in body


def test_dc_view_exposes_hosts_data_stores():
    src = Path("src/pages/dc_view.py").read_text(encoding="utf-8")
    assert 'id="hosts-data-classic"' in src
    assert 'id="hosts-data-hyperconv"' in src
