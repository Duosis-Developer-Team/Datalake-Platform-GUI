"""P7: SAN and backup fetch groups must be issued via parallel_execute, not serially."""
import ast
from pathlib import Path


def _func_source(name: str) -> str:
    src = Path("src/pages/dc_view.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node) or ""
    raise AssertionError(f"{name} not found")


def _parallel_execute_calls(body: str) -> list[int]:
    """Return the character offsets of every 'parallel_execute(' in body."""
    import re
    return [m.start() for m in re.finditer(r"parallel_execute\(", body)]


def test_san_and_backup_use_parallel_execute():
    body = _func_source("build_dc_view")
    assert "get_dc_san_port_usage" in body and "get_dc_san_health" in body
    assert "get_dc_netbackup_pools" in body and "get_dc_zerto_sites" in body

    # --- SAN: get_dc_san_port_usage must appear INSIDE a parallel_execute({...}) dict ---
    # Strategy: find the parallel_execute call that is closest *before*
    # get_dc_san_port_usage and verify it's within ~400 chars of the key.
    calls = _parallel_execute_calls(body)
    san_offset = body.index("get_dc_san_port_usage")
    # There must be a parallel_execute( that starts before san_offset
    # and the san call must be within 500 chars after that parallel_execute(
    san_in_parallel = any(
        c < san_offset < c + 500
        for c in calls
    )
    assert san_in_parallel, (
        "get_dc_san_port_usage is NOT inside a parallel_execute block — SAN fetch is still serial"
    )

    # --- Backup: get_dc_netbackup_pools must appear INSIDE a parallel_execute({...}) dict ---
    nb_offset = body.index("get_dc_netbackup_pools")
    nb_in_parallel = any(
        c < nb_offset < c + 500
        for c in calls
    )
    assert nb_in_parallel, (
        "get_dc_netbackup_pools is NOT inside a parallel_execute block — backup fetch is still serial"
    )

    # net + storage (existing) + san + backup (new) => at least 6 parallel_execute calls
    # (batch1, batch2, net, storage, san, backup = 6 minimum)
    assert len(calls) >= 6, (
        f"Expected at least 6 parallel_execute calls, found {len(calls)}"
    )
