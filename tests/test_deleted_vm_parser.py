"""Unit tests for shared.customer.deleted_vm_parser (pure, no DB).

Company names are fictional placeholders; the fixtures mirror the *structure* of
real deleted-VM names (trailing DD_MM_YYYY, keyword typos, two-date traps) without
any real customer data.
"""
import datetime as dt
import unittest

from shared.customer.deleted_vm_parser import (
    DeletedVmInfo,
    build_registry_row,
    parse_deleted_vm,
)


class TestParseDeletedVm(unittest.TestCase):
    def test_basic_trailing_date(self):
        info = parse_deleted_vm("_Ornek_Ltd-App01_Silinecek_27_07_2026")
        self.assertEqual(info.planned_date, dt.date(2026, 7, 27))
        self.assertEqual(info.request_date, dt.date(2026, 7, 13))  # planned - 14d
        self.assertEqual(info.customer, "Ornek_Ltd")

    def test_keyword_typo_ignored(self):
        # "Silenecek" (typo) must not matter — we anchor on the date.
        info = parse_deleted_vm("_Deneme_Sirket-Erp_Dev_Silenecek_05_03_2026")
        self.assertEqual(info.planned_date, dt.date(2026, 3, 5))
        self.assertEqual(info.request_date, dt.date(2026, 2, 19))
        self.assertEqual(info.customer, "Deneme_Sirket")

    def test_turkish_typo_variant(self):
        info = parse_deleted_vm("_Test_As-Sophos_Sİlineek_30_07_2026")
        self.assertEqual(info.planned_date, dt.date(2026, 7, 30))
        self.assertEqual(info.customer, "Test_As")

    def test_two_dates_takes_trailing(self):
        # middle "29:06_2026" is a restore stamp; the DELETE date is the last one.
        info = parse_deleted_vm("_Acme-App_Restore_29:06_2026_Silinecek_20_07_2026")
        self.assertEqual(info.planned_date, dt.date(2026, 7, 20))
        self.assertEqual(info.customer, "Acme")

    def test_date_without_keyword(self):
        # some names carry a trailing date but no Silinecek word at all.
        info = parse_deleted_vm("_Initech_Grup-Alosoft_01_04_2026")
        self.assertEqual(info.planned_date, dt.date(2026, 4, 1))
        self.assertEqual(info.customer, "Initech_Grup")

    def test_no_date_returns_none(self):
        self.assertIsNone(parse_deleted_vm("_Globex-Prod-Web1"))
        self.assertIsNone(parse_deleted_vm("_Export-Some_Holding-Prodsapp1"))

    def test_invalid_date_returns_none(self):
        self.assertIsNone(parse_deleted_vm("_Foo-Bar_99_99_2026"))
        self.assertIsNone(parse_deleted_vm("_Foo-Bar_32_01_2026"))

    def test_separator_variants(self):
        for name, expected in [
            ("_Foo_Ltd-Vm_30-07-2026", dt.date(2026, 7, 30)),
            ("_Foo_Ltd-Vm_30.07.2026", dt.date(2026, 7, 30)),
            ("_Foo_Ltd-Vm_Silinecek_1_4_2026", dt.date(2026, 4, 1)),  # single-digit d/m
        ]:
            with self.subTest(name=name):
                info = parse_deleted_vm(name)
                self.assertIsNotNone(info, name)
                self.assertEqual(info.planned_date, expected)

    def test_customer_none_when_no_dash(self):
        # no '-' means we can't split customer from vm name reliably.
        info = parse_deleted_vm("_JustAName_Silinecek_10_08_2026")
        self.assertEqual(info.planned_date, dt.date(2026, 8, 10))
        self.assertIsNone(info.customer)

    def test_robustness(self):
        for junk in ["", "   ", None, "_", "___", "no_underscore_prefix_01_01_2026"]:
            with self.subTest(junk=junk):
                # names not starting with '_' are not deleted-VMs
                if junk and junk.startswith("_") and junk.strip("_"):
                    continue
                self.assertIsNone(parse_deleted_vm(junk))

    def test_non_underscore_prefixed_is_not_deleted(self):
        # a normal live VM that merely happens to end in a date is NOT a deleted VM
        self.assertIsNone(parse_deleted_vm("Ornek_Ltd-Report_01_01_2026"))


class TestBuildRegistryRow(unittest.TestCase):
    TODAY = dt.date(2026, 7, 16)

    def test_still_emitting_has_null_actual(self):
        # last metric yesterday -> still running -> actual_delete_date None (overdue if planned passed)
        row = build_registry_row(
            "vmware", "_Ornek_Ltd-App_Silinecek_01_05_2026",
            first_seen=dt.date(2026, 4, 17), last_seen=dt.date(2026, 7, 15), today=self.TODAY,
        )
        self.assertEqual(row["platform"], "vmware")
        self.assertEqual(row["planned_date"], dt.date(2026, 5, 1))
        self.assertEqual(row["request_date"], dt.date(2026, 4, 17))
        self.assertEqual(row["first_seen"], dt.date(2026, 4, 17))
        self.assertIsNone(row["actual_delete_date"])  # still emitting

    def test_stopped_emitting_sets_actual(self):
        # no metrics for >3 days -> actually deleted; actual = last_seen
        row = build_registry_row(
            "nutanix", "_Deneme_As-Db_Silinecek_10_03_2026",
            first_seen=dt.date(2026, 2, 24), last_seen=dt.date(2026, 3, 20), today=self.TODAY,
        )
        self.assertEqual(row["actual_delete_date"], dt.date(2026, 3, 20))

    def test_unparseable_name_returns_none(self):
        self.assertIsNone(build_registry_row(
            "vmware", "_Globex-NoDateHere",
            first_seen=dt.date(2026, 1, 1), last_seen=dt.date(2026, 1, 2), today=self.TODAY,
        ))


if __name__ == "__main__":
    unittest.main()
