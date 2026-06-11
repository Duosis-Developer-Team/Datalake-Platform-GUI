from __future__ import annotations

from dash import html

from src.pages.dc_view import (
    _build_compute_capacity_rows,
    _capacity_pct_badge_color,
    _capacity_resource_table,
    _cpu_allocation_gauge_block,
)


class TestCapacityPctBadgeColor:
    def test_thresholds(self):
        assert _capacity_pct_badge_color(50) == "indigo"
        assert _capacity_pct_badge_color(70) == "yellow"
        assert _capacity_pct_badge_color(90) == "red"


class TestBuildComputeCapacityRows:
    def test_three_rows_physical_allocation_only(self):
        rows = _build_compute_capacity_rows(
            cpu_cap=5317.44,
            cpu_alloc_ghz=33811.0,
            cpu_alloc_pct=635.9,
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
        assert "sales" not in rows[0]
        assert rows[0]["bar_pct"] == 635.9
        assert rows[1]["max_util"][1] == 70.0
        assert rows[1]["max_util"][1] != rows[1]["allocation"][1]


class TestCapacityResourceTable:
    def test_renders_three_body_rows(self):
        rows = _build_compute_capacity_rows(
            cpu_cap=100.0,
            cpu_alloc_ghz=120.0,
            cpu_alloc_pct=120.0,
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

    def test_table_has_five_columns_including_bar(self):
        rows = _build_compute_capacity_rows(
            cpu_cap=100.0,
            cpu_alloc_ghz=120.0,
            cpu_alloc_pct=120.0,
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
        header_row = table.children[0].children[0].children[0]
        assert len(header_row.children) == 5
        assert header_row.children[2].children == "Physical allocation"


class TestCpuAllocationGaugeBlock:
    def test_physical_overalloc_badge(self):
        block = _cpu_allocation_gauge_block(
            {"cpu_alloc_ghz_vm": 150.0, "cpu_overallocated_real": True},
            cpu_cap=100.0,
        )
        assert "Overallocated" in str(block)
        assert "Overallocated for Sales" not in str(block)
