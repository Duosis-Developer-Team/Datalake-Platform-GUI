"""Shape tests for per-host CPU peak / CPU+RAM average queries.

These are string-shape assertions, not DB round-trips: the repo has no test
database, and the risk being guarded is a malformed query shape (wrong
placeholder count, averaging the wrong column, forgetting the cluster filter).
"""
from app.db.queries import nutanix as nq
from app.db.queries import vmware as vq


class TestClassicHostCpuPeak:
    def test_picks_worst_timestamp_per_host(self):
        sql = vq.CLASSIC_HOST_CPU_PEAK
        assert "DISTINCT ON (vmhost)" in sql
        # Peak = highest utilisation ratio, not merely the highest absolute GHz.
        assert "ORDER BY vmhost, (used_ghz / NULLIF(cap_ghz, 0)) DESC" in sql
        assert "public.vmhost_metrics" in sql

    def test_has_five_placeholders_matching_mem_peak(self):
        assert vq.CLASSIC_HOST_CPU_PEAK.count("%s") == vq.CLASSIC_HOST_MEM_PEAK.count("%s")

    def test_scoped_to_km_clusters_with_optional_filter(self):
        sql = vq.CLASSIC_HOST_CPU_PEAK
        assert "cluster ILIKE '%%KM%%'" in sql
        assert "cardinality(%s::text[]) = 0 OR cluster = ANY(%s::text[])" in sql


class TestClassicHostAvg:
    def test_averages_across_window_not_latest_snapshot(self):
        sql = vq.CLASSIC_HOST_AVG
        # CLASSIC_HOST_AVG has no CTE today, but the assertion should express
        # the actual invariant -- no per-host DISTINCT ON collapsing the window
        # to one row -- rather than accidentally passing on a blanket check.
        assert "DISTINCT ON (vmhost)" not in sql
        assert "AVG(cpu_ghz_used)" in sql
        assert "AVG(cpu_ghz_capacity)" in sql
        assert "AVG(memory_used_gb)" in sql
        assert "AVG(memory_capacity_gb)" in sql
        assert "GROUP BY vmhost" in sql

    def test_placeholder_count_matches_mem_peak(self):
        assert vq.CLASSIC_HOST_AVG.count("%s") == vq.CLASSIC_HOST_MEM_PEAK.count("%s")


class TestNutanixHostCpuPeak:
    def test_picks_worst_timestamp_and_converts_hz(self):
        sql = nq.NUTANIX_HOST_CPU_PEAK
        assert "DISTINCT ON (host_name)" in sql
        assert "1000000000.0" in sql, "Hz must be converted to GHz in SQL"
        assert "public.nutanix_host_metrics" in sql
        assert "ORDER BY host_name, (used_hz / NULLIF(cap_hz, 0)) DESC" in sql

    def test_placeholder_count_matches_mem_peak(self):
        assert nq.NUTANIX_HOST_CPU_PEAK.count("%s") == nq.NUTANIX_HOST_MEM_PEAK.count("%s")


class TestNutanixHostAvg:
    def test_averages_and_converts_both_units(self):
        sql = nq.NUTANIX_HOST_AVG
        # DISTINCT ON (cluster_uuid) in the dc_clusters CTE is legitimate --
        # it resolves cluster identity, exactly as NUTANIX_HOST_MEM_PEAK does.
        # What must NOT appear is a per-host DISTINCT ON, which would collapse
        # the window to a single row and defeat the average.
        assert "DISTINCT ON (host_name)" not in sql
        assert "DISTINCT ON (cluster_uuid)" in sql
        assert "AVG(" in sql
        assert "AVG(h.cpu_usage_avg)" in sql
        assert "AVG(h.total_cpu_capacity)" in sql
        assert "AVG(h.memory_usage_avg)" in sql
        assert "AVG(h.total_memory_capacity)" in sql
        assert "GROUP BY h.host_name" in sql
        assert "1000000000.0" in sql, "Hz -> GHz"
        assert "1073741824.0" in sql, "bytes -> GB"

    def test_placeholder_count_matches_mem_peak(self):
        assert nq.NUTANIX_HOST_AVG.count("%s") == nq.NUTANIX_HOST_MEM_PEAK.count("%s")
