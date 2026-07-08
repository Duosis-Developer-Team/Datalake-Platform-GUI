"""Unit tests for shared.nutanix.snapshot_helpers (pure, no DB)."""
import datetime as dt
import unittest

from shared.nutanix.snapshot_helpers import (
    parse_customer, parse_retention, ip_to_nutanix_uuid, uuid_to_ip,
    split_vms, enrich_snapshot_rows, aggregate_snapshots,
)


class TestParseCustomer(unittest.TestCase):
    def test_clean_prefix_from_pd_name(self):
        self.assertEqual(parse_customer("Alisan_Lojistik-1Day_30RP"), "Alisan_Lojistik")

    def test_alphanumeric_customer_kept(self):
        self.assertEqual(parse_customer("12mtech-1Days_7RP"), "12mtech")

    def test_generic_schedule_returns_none(self):
        self.assertIsNone(parse_customer("1Days_10RP"))
        self.assertIsNone(parse_customer("1Day7RP"))

    def test_no_dash_falls_back_to_vm_names(self):
        self.assertEqual(
            parse_customer("Capa_Medikal_1Days_7RP", "Capa_Medikal-App1, Capa_Medikal-App2"),
            "Capa_Medikal",
        )

    def test_all_unparseable_returns_none(self):
        self.assertIsNone(parse_customer("1_VC1DC13_Backup", None))


class TestParseRetention(unittest.TestCase):
    def test_prefers_max_snapshots(self):
        self.assertEqual(parse_retention(30, "X-1Day_7RP"), 30)

    def test_falls_back_to_rp_in_name(self):
        self.assertEqual(parse_retention(None, "Zorlu_Zes-1Day_7RP"), 7)

    def test_returns_none_when_unknown(self):
        self.assertIsNone(parse_retention(None, "no-retention-token"))


class TestIpUuid(unittest.TestCase):
    def test_ip_to_uuid(self):
        self.assertEqual(ip_to_nutanix_uuid("10.34.2.98"), "nutanix-10.34.2.98")

    def test_uuid_to_ip_strips_prefix(self):
        self.assertEqual(uuid_to_ip("nutanix-10.34.2.98"), "10.34.2.98")

    def test_uuid_to_ip_passthrough_without_prefix(self):
        self.assertEqual(uuid_to_ip("10.34.2.98"), "10.34.2.98")

    def test_split_vms(self):
        self.assertEqual(split_vms("A-1, A-2 , A-3"), ["A-1", "A-2", "A-3"])
        self.assertEqual(split_vms(None), [])


class TestEnrichAndAggregate(unittest.TestCase):
    def _raw(self):
        # nutanix_ip, pd_name, state, vm_names, miss_name, miss_type, sched_type,
        # max_snaps, size, start_time, create_time, expiry_time, snapshot_id
        return [
            ("10.34.2.98", "Zorlu_Zes-1Day_7RP", "AVAILABLE", "Zorlu_Zes-Terminal",
             None, None, "DAILY", 7, 4940000000,
             dt.datetime(2025, 3, 25, 5, 44), dt.datetime(2026, 7, 8, 5, 44),
             dt.datetime(2026, 7, 15, 5, 44), "snap-1"),
            ("10.34.2.98", "Alisan-1Day_30RP", "AVAILABLE", None,
             "Alisan-Ghost", "Virtual Machine", "MONTHLY", None, 100,
             dt.datetime(2025, 1, 1), dt.datetime(2026, 7, 8, 4, 15),
             dt.datetime(2026, 8, 7, 4, 15), "snap-2"),
        ]

    def test_enrich_maps_cluster_customer_and_as_of(self):
        rows, as_of = enrich_snapshot_rows(self._raw(), {"10.34.2.98": "DC13-G17-HYBRID"})
        self.assertEqual(rows[0]["cluster"], "DC13-G17-HYBRID")
        self.assertEqual(rows[0]["customer"], "Zorlu_Zes")
        self.assertEqual(rows[0]["retention"], 7)
        self.assertEqual(rows[1]["retention"], 30)  # from name fallback
        self.assertEqual(rows[1]["missing_entity"], "Alisan-Ghost")
        self.assertEqual(as_of, "2026-07-08T05:44:00")  # max create_time
        self.assertEqual(rows[0]["create_time"], "2026-07-08T05:44:00")

    def test_enrich_without_cluster_map_blank(self):
        rows, _ = enrich_snapshot_rows(self._raw(), None)
        self.assertEqual(rows[0]["cluster"], "")

    def test_aggregate(self):
        rows, _ = enrich_snapshot_rows(self._raw(), {})
        agg = aggregate_snapshots(rows)
        self.assertEqual(agg["total_snapshots"], 2)
        self.assertEqual(agg["total_size_bytes"], 4940000100)
        self.assertEqual(agg["protected_vms"], 1)  # only snap-1 has a VM
        self.assertEqual(agg["missing_entities"], 1)
        self.assertEqual(agg["schedule_type_breakdown"], {"DAILY": 1, "MONTHLY": 1})
        self.assertEqual(agg["state_breakdown"], {"AVAILABLE": 2})

    def test_aggregate_empty(self):
        agg = aggregate_snapshots([])
        self.assertEqual(agg["total_snapshots"], 0)
        self.assertEqual(agg["total_size_bytes"], 0)
        self.assertEqual(agg["schedule_type_breakdown"], {})


if __name__ == "__main__":
    unittest.main()
