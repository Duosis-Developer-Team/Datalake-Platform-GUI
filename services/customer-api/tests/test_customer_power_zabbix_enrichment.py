"""Tests for Power LPAR Zabbix enrichment query and adapter mapping."""

from __future__ import annotations

from app.db.queries import customer as cq


def test_power_lpar_detail_query_joins_zabbix_table():
    sql = cq.CUSTOMER_POWER_LPAR_DETAIL_LIST
    assert "raw_zabbix_hana_linux_host_metrics" in sql
    assert "ibm_partition_name" in sql
    assert "COALESCE(zl.agent_hostname, l.lparname)" in sql
    assert "Power HMC + Zabbix" in sql
    assert '"Disk (GB)"' in sql


def test_power_lpar_detail_query_parameter_count():
    sql = cq.CUSTOMER_POWER_LPAR_DETAIL_LIST
    assert sql.count("%s") == 10


def test_power_vm_list_mapping_indices():
    row = (
        "hana01.example",
        "BOYNER_SAP01",
        "Power HMC + Zabbix",
        4.0,
        10.0,
        20.0,
        30.0,
        64.0,
        45.0,
        62.0,
        88.0,
        500.0,
        120.0,
        180.0,
        "running",
    )
    mapped = {
        "name": row[0],
        "lpar_name": row[1],
        "source": row[2],
        "cpu": float(row[3]),
        "cpu_pct_min": float(row[4]),
        "cpu_pct_avg": float(row[5]),
        "cpu_pct_max": float(row[6]),
        "memory_gb": float(row[7]),
        "mem_pct_min": float(row[8]),
        "mem_pct_avg": float(row[9]),
        "mem_pct_max": float(row[10]),
        "disk_gb": float(row[11]),
        "disk_used_min_gb": float(row[12]),
        "disk_used_max_gb": float(row[13]),
        "state": row[14],
    }
    assert mapped["name"] == "hana01.example"
    assert mapped["lpar_name"] == "BOYNER_SAP01"
    assert mapped["disk_gb"] == 500.0
    assert mapped["mem_pct_avg"] == 62.0
