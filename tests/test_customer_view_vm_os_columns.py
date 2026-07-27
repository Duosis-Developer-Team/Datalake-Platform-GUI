"""Customer View virtualization tables: guest-OS column + perspective column hiding.

Two separate asks:

1. Every VM table gains an "İşletim Sistemi" column — the customer must be able to
   see which of their guests is Windows/RHEL/SUSE, which is what the licence row on
   the summary is counting.
2. In the **customer** perspective the Source and Cluster columns are hidden: which
   hypervisor and which cluster a VM sits on is Bulutistan's internal topology, not
   something a customer is shown. Manager perspective keeps them.
"""
from __future__ import annotations

from dash import html

from src.pages.customer_view import (
    _tab_classic,
    _tab_hyperconv,
    _tab_power,
    _tab_pure_nutanix,
)

_VM = {
    "name": "acme-srv01",
    "source": "VMware",
    "cluster": "DC13-KM-CLS-NVME",
    "vmhost": "esx-01",
    "cpu": 4,
    "memory_gb": 16.0,
    "disk_gb": 100.0,
    "guest_os": "Microsoft Windows Server 2022 (64-bit)",
    "os_family": "windows",
}

_LPAR = {
    "name": "acme-lpar01",
    "lpar_name": "acme-lpar01",
    "source": "Power HMC",
    "cpu": 2.0,
    "memory_gb": 32.0,
    "disk_gb": 200.0,
    "state": "Running",
    "guest_os": "Linux - SUSE",
    "os_family": "suse",
}


def _header_cells(component) -> list[str]:
    """Every <th> string in the rendered component."""
    out: list[str] = []

    def walk(node):
        if isinstance(node, (list, tuple)):
            for n in node:
                walk(n)
            return
        if isinstance(node, html.Th):
            ch = node.children
            if isinstance(ch, str):
                out.append(ch)
        children = getattr(node, "children", None)
        if children is not None:
            walk(children)

    walk(component)
    return out


def _text(component) -> str:
    return str(component)


# --- 1. guest OS column -----------------------------------------------------

def test_classic_table_has_an_os_column():
    assert "İşletim Sistemi" in _header_cells(_tab_classic({"vm_list": [_VM]}, None))


def test_hyperconv_table_has_an_os_column():
    assert "İşletim Sistemi" in _header_cells(_tab_hyperconv({"vm_list": [_VM]}, {}, None))


def test_pure_nutanix_table_has_an_os_column():
    assert "İşletim Sistemi" in _header_cells(_tab_pure_nutanix({"vm_list": [_VM]}, None))


def test_power_table_has_an_os_column():
    assert "İşletim Sistemi" in _header_cells(_tab_power({"vm_list": [_LPAR]}, None))


def test_os_value_is_rendered_for_the_vm():
    assert "Microsoft Windows Server 2022" in _text(_tab_classic({"vm_list": [_VM]}, None))


def test_vm_without_an_os_signal_renders_a_placeholder_not_a_guess():
    blind = {**_VM, "guest_os": None, "os_family": "unknown"}
    rendered = _text(_tab_pure_nutanix({"vm_list": [blind]}, None))
    assert "Windows" not in rendered
    assert "RHEL" not in rendered


# --- 2. perspective column hiding ------------------------------------------

def test_manager_perspective_keeps_source_and_cluster():
    headers = _header_cells(_tab_hyperconv({"vm_list": [_VM]}, {}, None, show_infra_columns=True))
    assert "Source" in headers
    assert "Cluster" in headers


def test_customer_perspective_hides_source_and_cluster():
    headers = _header_cells(_tab_hyperconv({"vm_list": [_VM]}, {}, None, show_infra_columns=False))
    assert "Source" not in headers
    assert "Cluster" not in headers
    assert "İşletim Sistemi" in headers


def test_customer_perspective_hides_cluster_on_classic_too():
    headers = _header_cells(_tab_classic({"vm_list": [_VM]}, None, show_infra_columns=False))
    assert "Cluster" not in headers
    assert "VM Name" in headers


def test_customer_perspective_hides_source_and_cluster_on_pure_nutanix():
    headers = _header_cells(_tab_pure_nutanix({"vm_list": [_VM]}, None, show_infra_columns=False))
    assert "Source" not in headers
    assert "Cluster" not in headers


def test_customer_perspective_does_not_leak_cluster_values_into_the_body():
    rendered = _text(_tab_hyperconv({"vm_list": [_VM]}, {}, None, show_infra_columns=False))
    assert "DC13-KM-CLS-NVME" not in rendered


def test_hiding_columns_keeps_row_and_header_widths_in_step():
    """A row with more cells than its header row renders a visually broken table.
    Checked per table, since a tab renders several."""
    for build in (
        lambda **kw: _tab_classic({"vm_list": [_VM]}, None, **kw),
        lambda **kw: _tab_hyperconv({"vm_list": [_VM]}, {}, None, **kw),
        lambda **kw: _tab_pure_nutanix({"vm_list": [_VM]}, None, **kw),
        lambda **kw: _tab_power({"vm_list": [_LPAR]}, None, **kw),
    ):
        for show in (True, False):
            tables = _table_shapes(build(show_infra_columns=show))
            assert tables, "expected at least one rendered table"
            for n_head, row_widths in tables:
                assert row_widths, "expected at least one rendered row"
                assert all(n == n_head for n in row_widths), (show, n_head, row_widths)


def _table_shapes(component) -> list[tuple[int, list[int]]]:
    """(header cell count, [body row cell counts]) for each rendered table."""
    out: list[tuple[int, list[int]]] = []

    def row_widths(node) -> list[int]:
        found: list[int] = []

        def walk(n):
            if isinstance(n, (list, tuple)):
                for x in n:
                    walk(x)
                return
            if isinstance(n, html.Tr):
                cells = n.children if isinstance(n.children, (list, tuple)) else [n.children]
                tds = [c for c in cells if isinstance(c, html.Td)]
                if tds:
                    found.append(len(tds))
            ch = getattr(n, "children", None)
            if ch is not None:
                walk(ch)

        walk(node)
        return found

    def walk(node):
        if isinstance(node, (list, tuple)):
            for n in node:
                walk(n)
            return
        if isinstance(node, html.Thead):
            return
        if type(node).__name__ == "Table":
            children = node.children if isinstance(node.children, (list, tuple)) else [node.children]
            heads = [c for c in children if isinstance(c, html.Thead)]
            bodies = [c for c in children if isinstance(c, html.Tbody)]
            if heads and bodies:
                out.append((len(_header_cells(heads[0])), row_widths(bodies[0])))
            return
        children = getattr(node, "children", None)
        if children is not None:
            walk(children)

    walk(component)
    return out
