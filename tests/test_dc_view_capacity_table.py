from __future__ import annotations

from dash import html

from src.pages.dc_view import (
    _build_compute_capacity_rows,
    _capacity_pct_badge_color,
    _capacity_resource_table,
)


class TestCapacityPctBadgeColor:
    def test_thresholds(self):
        assert _capacity_pct_badge_color(50) == "indigo"
        assert _capacity_pct_badge_color(70) == "yellow"
        assert _capacity_pct_badge_color(90) == "red"


class TestBuildComputeCapacityRows:
    def test_three_rows_with_cpu_sales(self):
        rows = _build_compute_capacity_rows(
            cpu_cap=5317.44,
            cpu_alloc_ghz=33811.0,
            cpu_alloc_sales=14787.0,
            cpu_alloc_pct=635.9,
            cpu_alloc_pct_sales=278.1,
            cpu_pct_max=60.4,
            cpu_pct=55.0,
            mem_cap=89568.0,
            mem_alloc_gb=75000.0,
            mem_alloc_pct=83.7,
            mem_pct_max=70.0,
            mem_pct=65.0,
            stor_cap_gb=1000000.0,
            stor_provisioned_gb=500000.0,
            stor_used_gb=200000.0,
            stor_alloc_vm_pct=50.0,
            stor_pct=20.0,
        )
        assert len(rows) == 3
        assert rows[0]["label"] == "CPU"
        assert rows[0]["sales"] is not None
        assert rows[1]["sales"] is None
        assert rows[2]["sales"] is None
        assert rows[0]["bar_pct"] == 635.9


class TestCapacityResourceTable:
    def test_renders_three_body_rows(self):
        rows = _build_compute_capacity_rows(
            cpu_cap=100.0,
            cpu_alloc_ghz=120.0,
            cpu_alloc_sales=110.0,
            cpu_alloc_pct=120.0,
            cpu_alloc_pct_sales=110.0,
            cpu_pct_max=50.0,
            cpu_pct=40.0,
            mem_cap=1000.0,
            mem_alloc_gb=800.0,
            mem_alloc_pct=80.0,
            mem_pct_max=60.0,
            mem_pct=55.0,
            stor_cap_gb=10000.0,
            stor_provisioned_gb=5000.0,
            stor_used_gb=2000.0,
            stor_alloc_vm_pct=50.0,
            stor_pct=20.0,
        )
        table = _capacity_resource_table(rows)
        assert isinstance(table, html.Div)
        tbody = table.children[0].children[1]
        assert len(tbody.children) == 3

    def test_memory_sales_cell_is_dash(self):
        rows = _build_compute_capacity_rows(
            cpu_cap=100.0,
            cpu_alloc_ghz=120.0,
            cpu_alloc_sales=110.0,
            cpu_alloc_pct=120.0,
            cpu_alloc_pct_sales=110.0,
            cpu_pct_max=50.0,
            cpu_pct=40.0,
            mem_cap=1000.0,
            mem_alloc_gb=800.0,
            mem_alloc_pct=80.0,
            mem_pct_max=60.0,
            mem_pct=55.0,
            stor_cap_gb=10000.0,
            stor_provisioned_gb=5000.0,
            stor_used_gb=2000.0,
            stor_alloc_vm_pct=50.0,
            stor_pct=20.0,
        )
        table = _capacity_resource_table(rows)
        mem_row = table.children[0].children[1].children[1]
        sales_cell = mem_row.children[3]
        assert sales_cell.children == "—"
