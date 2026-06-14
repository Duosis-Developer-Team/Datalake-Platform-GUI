"""Topology enrichment must batch per-DC category counts into one pass.

Regression guard for the connection-pool exhaustion bug: the old
_enrich_topology_payload called _category_counts_for_dc per node, and each
call issued ~4 queries (one targets fetch + three identical run-level
lookups). With ~80 DCs that is ~320 queries per topology build, and several
endpoints build the topology concurrently, exhausting the 8-conn pool.

The fix computes the run-level sets ONCE and fetches all active targets in a
single query, so the query count is constant regardless of DC count.
"""

from __future__ import annotations

from unittest.mock import patch

from app.db.queries import collectors


def _make_payload(dc_codes):
    return {
        "last_prod_run_id": "run-1",
        "nodes": [
            {
                "dc_code": dc,
                "location_name": dc,
                "proxy_config_status": "configured",
                "loki_sync_status": "loki_synced",
                "proxies": [],
            }
            for dc in dc_codes
        ],
    }


class _FakePool:
    """Routes fetch_all/fetch_one by SQL content and counts calls."""

    def __init__(self, targets, removed=(), fails=()):
        self.targets = targets
        self.removed = list(removed)
        self.fails = list(fails)
        self.fetch_all_calls = 0
        self.fetch_one_calls = 0

    def fetch_all(self, query, params=None):
        self.fetch_all_calls += 1
        if "collector_diff_log" in query:
            return [{"ip": ip, "proxy_id": pid} for ip, pid in self.removed]
        if "collector_check_log" in query:
            return [{"ip": ip, "proxy_id": pid} for ip, pid in self.fails]
        if "collector_target" in query:
            # Bulk enrichment fetch carries no params (all DCs at once).
            assert not params, "enrichment target fetch must not filter by DC"
            return self.targets
        raise AssertionError(f"unexpected fetch_all: {query[:60]}")

    def fetch_one(self, query, params=None):
        self.fetch_one_calls += 1
        if "MAX(finished_at)" in query and "collector_sync_log" in query:
            return {"finished_at": "2026-06-11T00:00:00Z"}
        raise AssertionError(f"unexpected fetch_one: {query[:60]}")


def test_enrichment_query_count_is_constant_across_dc_count():
    """50 DCs must not produce 50× the queries of 1 DC."""

    def run(n):
        targets = [
            {
                "dc_code": f"DC{i}",
                "ip": f"10.0.0.{i}",
                "proxy_id": f"P{i}",
                "extra": {"platform_status": "monitored"},
                "last_distributed_at": "2026-06-10T00:00:00Z",
            }
            for i in range(n)
        ]
        fake = _FakePool(targets)
        with patch.object(collectors, "pool", fake):
            collectors._enrich_topology_payload(_make_payload([f"DC{i}" for i in range(n)]))
        return fake.fetch_all_calls + fake.fetch_one_calls

    one = run(1)
    fifty = run(50)
    assert one == fifty, f"query count scales with DC count: {one} vs {fifty}"
    # 3 fetch_all (removed, fails, bulk targets) + 1 fetch_one (run finished).
    assert fifty == 4


def test_enrichment_assigns_correct_per_dc_status():
    targets = [
        # DC1: one monitored target -> connected
        {
            "dc_code": "DC1",
            "ip": "10.0.0.1",
            "proxy_id": "P1",
            "extra": {"platform_status": "monitored"},
            "last_distributed_at": "2026-06-10T00:00:00Z",
        },
        # DC2: connectivity fail -> connectivity_issue
        {
            "dc_code": "DC2",
            "ip": "10.0.0.2",
            "proxy_id": "P2",
            "extra": {"platform_status": "monitored"},
            "last_distributed_at": "2026-06-10T00:00:00Z",
        },
    ]
    fake = _FakePool(targets, fails=[("10.0.0.2", "P2")])
    with patch.object(collectors, "pool", fake):
        payload = collectors._enrich_topology_payload(_make_payload(["DC1", "DC2", "DC3"]))

    by_dc = {n["dc_code"]: n for n in payload["nodes"]}
    assert by_dc["DC1"]["environment_status"] == "connected"
    assert by_dc["DC1"]["connectivity_issue_count"] == 0
    assert by_dc["DC2"]["environment_status"] == "connectivity_issue"
    assert by_dc["DC2"]["connectivity_issue_count"] == 1
    # DC3 has no targets -> treated as connected with zero issues.
    assert by_dc["DC3"]["environment_status"] == "connected"
    assert by_dc["DC3"]["connectivity_issue_count"] == 0
    assert payload["connected_environment_count"] == 2
    assert payload["connectivity_issue_environment_count"] == 1
