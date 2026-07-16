"""Smoke tests for unique-jobs inventory panel helpers."""

from src.components.backup_unique_jobs_panel import (
    build_unique_jobs_inventory_section,
    build_unique_jobs_visuals,
    unique_jobs_table,
)


def test_unique_jobs_table_renders_rows():
    items = [
        {"name": "Job-A", "type": "Backup", "status": "success", "source_ip": "10.0.0.1"},
    ]
    out = unique_jobs_table("veeam", items)
    assert out is not None


def test_build_unique_jobs_visuals_empty_totals():
    kpis, donut, status = build_unique_jobs_visuals({}, "veeam")
    assert kpis is not None
    assert donut is not None
    assert status is not None


def test_build_unique_jobs_inventory_section_layout():
    panel = build_unique_jobs_inventory_section(
        "veeam",
        scope="dc",
        initial={
            "rows": [
                {
                    "name": "Job-A",
                    "type": "Backup",
                    "status": "success",
                    "source_ip": "10.0.0.1",
                }
            ],
            "totals": {
                "total_jobs": 1,
                "by_status": {"success": 1},
                "by_type": {"Backup": 1},
            },
        },
    )
    assert panel is not None
