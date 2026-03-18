import unittest
from unittest.mock import patch, MagicMock

from src.services import sla_service
from src.services import cache_service as cache


class TestSlaService(unittest.TestCase):
    def setUp(self):
        cache.clear()

    def test_parse_dc_code_from_group_name(self):
        self.assertEqual(sla_service._parse_dc_code("Equinix IL2 - DC13"), "DC13")
        self.assertEqual(sla_service._parse_dc_code("AzinTelecom - AZ11"), "AZ11")
        self.assertEqual(sla_service._parse_dc_code("Equinix FR2 - ICT11"), "ICT11")
        self.assertIsNone(sla_service._parse_dc_code("No code here"))

    def test_build_entries_minutes_to_hours(self):
        payload = {
            "items": [
                {
                    "availability_pct": 99.9481,
                    "group_id": 3,
                    "group_name": "Equinix IL2 - DC13",
                    "period_min": 120.0,
                    "total_downtime_min": 30,
                }
            ]
        }
        by_dc, by_group = sla_service._build_entries(payload)
        self.assertIn("DC13", by_dc)
        e = by_dc["DC13"]
        self.assertAlmostEqual(e.period_hours, 2.0, places=6)
        self.assertAlmostEqual(e.downtime_hours, 0.5, places=6)
        self.assertIn(3, by_group)

    @patch("src.services.sla_service.requests.get")
    def test_refresh_sla_cache_fetches_and_caches(self, mock_get):
        tr = {"start": "2020-01-01", "end": "2020-01-02"}
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "items": [
                {
                    "availability_pct": 100.0,
                    "group_id": 7,
                    "group_name": "Isttelkom IBB - DC17",
                    "period_min": 60.0,
                    "total_downtime_min": 0,
                }
            ],
            "period_start": "2020-01-01T00:00:00",
            "period_end": "2020-01-02T00:00:00",
            "period_min": 60.0,
        }
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        out = sla_service.refresh_sla_cache(tr)
        self.assertIn("by_dc", out)
        self.assertIn("DC17", out["by_dc"])

        cached = cache.get(f"sla_availability:{tr['start']}:{tr['end']}")
        self.assertIsNotNone(cached)
        self.assertIn("DC17", cached["by_dc"])


if __name__ == "__main__":
    unittest.main()

