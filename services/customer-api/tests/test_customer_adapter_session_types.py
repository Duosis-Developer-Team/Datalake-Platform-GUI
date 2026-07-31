"""Veeam session_types ILIKE ANY + unique-jobs fallback for Sessions by Type."""
from __future__ import annotations

from app.adapters.customer_adapter import CustomerAdapter
from app.db.queries import customer as cq


def test_session_types_from_unique_job_rows_counts_types():
    rows = [
        ("t", "j1", "Acme-Backup", "Backup", "Success", "Success", "t", 1, "s", "vm", "10.0.0.1"),
        ("t", "j2", "Acme-Replica", "VSphereReplica", "Success", "Success", "t", 2, "s", "vm", "10.0.0.1"),
        ("t", "j3", "Acme-Backup-2", "Backup", "Failed", "Failed", "t", 1, "s", "vm", "10.0.0.1"),
        ("t", "j4", "Skip", None, "Success", "Success", "t", 1, "s", "vm", "10.0.0.1"),
        ("t", "j5", "Skip2", "  ", "Success", "Success", "t", 1, "s", "vm", "10.0.0.1"),
    ]
    out = CustomerAdapter.session_types_from_unique_job_rows(rows)
    assert out == [
        {"type": "Backup", "count": 2},
        {"type": "VSphereReplica", "count": 1},
    ]


def test_session_types_from_unique_job_rows_empty():
    assert CustomerAdapter.session_types_from_unique_job_rows([]) == []
    assert CustomerAdapter.session_types_from_unique_job_rows(None) == []


def test_veeam_and_zerto_queries_use_ilike_any_and_coalesce_types():
    assert "ILIKE ANY(%s)" in cq.CUSTOMER_VEEAM_DEFINED_SESSIONS
    assert "ILIKE ANY(%s)" in cq.CUSTOMER_VEEAM_SESSION_TYPES
    assert "ILIKE ANY(%s)" in cq.CUSTOMER_VEEAM_SESSION_PLATFORMS
    assert "ILIKE ANY(%s)" in cq.CUSTOMER_VEEAM_UNIQUE_JOBS_LATEST
    assert "COALESCE(NULLIF(session_type, ''), 'Unknown')" in cq.CUSTOMER_VEEAM_SESSION_TYPES
    assert "ILIKE ANY(%s)" in cq.CUSTOMER_ZERTO_PROTECTED_VMS
    assert "ILIKE ANY(%s)" in cq.CUSTOMER_ZERTO_PROVISIONED_STORAGE
    assert "ILIKE ANY(%s)" in cq.CUSTOMER_ZERTO_UNIQUE_VPGS_LATEST


def test_defined_sessions_synced_from_fallback_type_counts():
    """Mirror adapter rule: empty sessions table but jobs_states types → defined count."""
    types = CustomerAdapter.session_types_from_unique_job_rows(
        [
            ("t", "j1", "A", "Backup", "Success", "Success", "t", 1, "s", "vm", "ip"),
            ("t", "j2", "B", "VSphereReplica", "Success", "Success", "t", 1, "s", "vm", "ip"),
        ]
    )
    defined = 0
    if defined == 0 and types:
        defined = sum(int(t.get("count") or 0) for t in types)
    assert defined == 2
    assert {t["type"] for t in types} == {"Backup", "VSphereReplica"}


def test_partition_veeam_session_types():
    rows = [
        {"type": "Backup", "count": 2},
        {"type": "VSphereReplica", "count": 1},
        {"type": "ReplicaJob", "count": 3},
        {"type": "Unknown", "count": 1},
    ]
    buckets = CustomerAdapter.partition_veeam_session_types(rows)
    assert {r["type"] for r in buckets["backup"]} == {"Backup"}
    assert {r["type"] for r in buckets["replica"]} == {"VSphereReplica", "ReplicaJob"}
    assert {r["type"] for r in buckets["other"]} == {"Unknown"}
