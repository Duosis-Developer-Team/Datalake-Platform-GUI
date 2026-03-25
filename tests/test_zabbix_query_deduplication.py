import sys
import os
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'services', 'datacenter-api')))

from app.db.queries import zabbix_network
from app.db.queries import zabbix_storage

def test_interface_95th_percentile_deduplication():
    query = zabbix_network.INTERFACE_95TH_PERCENTILE
    assert "DISTINCT ON" in query.upper(), "INTERFACE_95TH_PERCENTILE must use DISTINCT ON to deduplicate incoming rows"

def test_interface_bandwidth_table_p95_deduplication():
    query = zabbix_network.INTERFACE_BANDWIDTH_TABLE_P95
    assert "DISTINCT ON" in query.upper(), "INTERFACE_BANDWIDTH_TABLE_P95 must use DISTINCT ON to deduplicate incoming rows"

def test_disk_health_performance_deduplication():
    query = zabbix_storage.DISK_HEALTH_PERFORMANCE
    assert "DISTINCT ON" in query.upper(), "DISK_HEALTH_PERFORMANCE stats CTE must use DISTINCT ON to deduplicate incoming rows"
