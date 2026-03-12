import unittest

from src.queries import s3 as s3q


class TestS3Queries(unittest.TestCase):
    def test_pool_latest_uses_new_capacity_columns(self):
        sql = s3q.POOL_LATEST
        self.assertIn("total_capacity_bytes", sql)
        self.assertIn("used_capacity_bytes", sql)
        self.assertNotIn("usable_size_bytes", sql)
        self.assertNotIn("used_physical_size_bytes", sql)

    def test_vault_latest_joins_inventory_for_quota(self):
        sql = s3q.VAULT_LATEST
        self.assertIn("raw_s3icos_vault_inventory", sql)
        self.assertIn("LATERAL", sql.upper())
        self.assertIn("hard_quota_bytes", sql)


if __name__ == "__main__":
    unittest.main()

