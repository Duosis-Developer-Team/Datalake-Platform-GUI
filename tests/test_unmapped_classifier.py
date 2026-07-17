"""Unit tests for shared.customer.unmapped_classifier (pure, no DB).

All company names below are fictional placeholders; they exist only to exercise
the matching rules (Turkish folding, legal-suffix keys, the <Customer>-<VMname>
convention, system-VM exclusion). No real customer data.
"""
import unittest

from shared.customer.unmapped_classifier import (
    OwnerMatcher,
    account_keys_from_names,
    build_unmapped_payload,
    classify_unmapped,
    guess_owner,
    norm,
    owner_matchers_from_mappings,
)


class TestNorm(unittest.TestCase):
    def test_turkish_fold_and_strip(self):
        self.assertEqual(norm("DENEME KOZMETİK SANAYİ VE TİCARET ANONİM ŞİRKETİ"),
                         "denemekozmetiksanayiveticaretanonimsirketi")

    def test_underscore_and_case(self):
        self.assertEqual(norm("Ornek_Kilit"), "ornekkilit")

    def test_empty_and_none(self):
        self.assertEqual(norm(""), "")
        self.assertEqual(norm(None), "")


class TestGuessOwner(unittest.TestCase):
    def setUp(self):
        # norm(account_name) -> display name (fictional placeholders)
        self.keys = {
            "ornekkilit": "Örnek Kilit A.Ş.",
            "denemekozmetiksanayiveticaretanonimsirketi": "DENEME KOZMETİK SANAYİ VE TİCARET A.Ş.",
            "denemekredi": "Deneme Kredi",
        }

    def test_dash_prefix_exact(self):
        self.assertEqual(guess_owner("Ornek_Kilit-AppServer01", self.keys), "Örnek Kilit A.Ş.")

    def test_turkish_folded_prefix(self):
        # VM prefix is a short form of a longer legal name -> fuzzy match
        self.assertEqual(guess_owner("deneme_Kozmetik-Sophos", self.keys),
                         "DENEME KOZMETİK SANAYİ VE TİCARET A.Ş.")

    def test_no_dash_startswith_account(self):
        # underscore-joined, no dash: still recognizably the same account
        self.assertEqual(guess_owner("Deneme_Kredi_LOG_Server", self.keys), "Deneme Kredi")

    def test_unknown_prefix_returns_none(self):
        self.assertIsNone(guess_owner("123host", self.keys))
        self.assertIsNone(guess_owner("342test", self.keys))


class TestClassifyUnmapped(unittest.TestCase):
    def setUp(self):
        self.owners = [
            OwnerMatcher(owner="Acme", kind="contains", value="Acme"),
            OwnerMatcher(owner="Globex", kind="prefix", value="Globex"),
        ]
        self.keys = {
            "ornekkilit": "Örnek Kilit A.Ş.",
            "denemekredi": "Deneme Kredi",
        }

    def _classify(self, names):
        return classify_unmapped(names, self.owners, self.keys)

    def test_owned_vm_excluded(self):
        # matches the Acme 'contains' / Globex 'prefix' matcher -> owned -> not returned
        rows = self._classify(["Acme_Region-Web01", "Globex-App1"])
        self.assertEqual(rows, [])

    def test_system_vms_excluded(self):
        rows = self._classify([
            "NTNX-21A847437-A-CVM",
            "NTNX-10-85-3-40-PCVM-1758992194",
            "vCLS-abc123",
            "Svm_Test",
        ])
        self.assertEqual(rows, [])

    def test_alias_gap_detected(self):
        rows = self._classify(["Ornek_Kilit-AppServer01"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].name, "Ornek_Kilit-AppServer01")
        self.assertEqual(rows[0].reason, "alias_gap")
        self.assertEqual(rows[0].guessed_owner, "Örnek Kilit A.Ş.")

    def test_orphan_detected(self):
        rows = self._classify(["123host"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].reason, "orphan")
        self.assertIsNone(rows[0].guessed_owner)

    def test_mixed_batch_counts(self):
        rows = self._classify([
            "Acme_Region-Web01",         # owned
            "vCLS-x",                    # system
            "Ornek_Kilit-Db",            # alias_gap
            "Deneme_Kredi_LOG_Server",   # alias_gap (no dash)
            "342test",                   # orphan
            "",                          # junk
            None,                        # junk
        ])
        reasons = sorted(r.reason for r in rows)
        self.assertEqual(reasons, ["alias_gap", "alias_gap", "orphan"])

    def test_robustness_blank_and_dashonly(self):
        rows = self._classify(["", "   ", "-", "---", None])
        self.assertEqual(rows, [])


class TestBuilders(unittest.TestCase):
    def test_owner_matchers_from_mappings_filters_sources(self):
        rows = [
            {"data_source": "virtualization", "match_method": "contains",
             "match_value": "Acme", "crm_account_name": "Acme"},
            {"data_source": "netbox_vm_customer", "match_method": "exact",
             "match_value": "Globex", "crm_account_name": "Globex"},
            {"data_source": "storage_ibm", "match_method": "contains",
             "match_value": "Ignore", "crm_account_name": "X"},  # non-VM source
            {"data_source": "virtualization", "match_method": "contains",
             "match_value": "", "crm_account_name": "Blank"},     # empty value
        ]
        matchers = owner_matchers_from_mappings(rows, display_names=["Initech A.Ş."])
        vals = sorted((m.kind, m.value) for m in matchers)
        self.assertEqual(vals, [("contains", "Acme"), ("contains", "Initech A.Ş."), ("exact", "Globex")])

    def test_account_keys_first_writer_wins(self):
        # "Acme" and "ACME_" both normalize to "acme"; first entry wins.
        keys = account_keys_from_names(["Acme", "ACME_", "", None])
        self.assertEqual(keys["acme"], "Acme")

    def test_account_keys_legal_suffix_stays_in_key(self):
        # Real-world: "A.Ş." folds into the key, so exact-prefix match won't fire
        # and guess_owner's fuzzy path does the work instead.
        keys = account_keys_from_names(["Örnek Kilit A.Ş."])
        self.assertIn("ornekkilitas", keys)
        self.assertNotIn("ornekkilit", keys)

    def test_build_payload_groups_and_counts(self):
        owners = [OwnerMatcher(owner="Acme", kind="contains", value="Acme")]
        keys = {"ornekkilit": "Örnek Kilit A.Ş."}
        payload = build_unmapped_payload(
            [
                ("Acme-Web01", "vmware"),        # owned
                ("vCLS-x", "nutanix"),            # system
                ("Ornek_Kilit-Db", "vmware"),    # alias_gap
                ("123host", "nutanix"),          # orphan
            ],
            owners, keys,
        )
        self.assertEqual(payload["total"], 2)
        self.assertEqual(payload["alias_gap_count"], 1)
        self.assertEqual(payload["orphan_count"], 1)
        # alias_gap sorts first
        self.assertEqual(payload["rows"][0]["reason"], "alias_gap")
        self.assertEqual(payload["rows"][0]["platform"], "vmware")
        self.assertEqual(payload["rows"][0]["guessed_owner"], "Örnek Kilit A.Ş.")


class TestOwnerMatcherUsesSharedSemantics(unittest.TestCase):
    def test_underscore_is_literal(self):
        m = OwnerMatcher(owner="Deneme", kind="contains", value="Deneme_Dr")
        self.assertTrue(m.matches("deneme_dr_prod"))
        self.assertFalse(m.matches("denemexdr"))

    def test_four_methods(self):
        self.assertTrue(OwnerMatcher("o", "prefix", "deneme").matches("deneme-vm01"))
        self.assertTrue(OwnerMatcher("o", "suffix", "vm01").matches("deneme-vm01"))
        self.assertTrue(OwnerMatcher("o", "exact", "deneme").matches("deneme"))
        self.assertFalse(OwnerMatcher("o", "exact", "deneme").matches("deneme-vm01"))
        self.assertTrue(OwnerMatcher("o", "contains", "deneme").matches("x-deneme-y"))

    def test_empty_value_never_matches(self):
        self.assertFalse(OwnerMatcher("o", "contains", "  ").matches("anything"))


class TestIdExactIsNotBroadenedToContains(unittest.TestCase):
    def test_id_exact_rule_claims_nothing(self):
        rows = [{
            "data_source": "virtualization",
            "match_method": "id_exact",
            "match_value": "5",
            "crm_account_name": "Deneme",
        }]
        matchers = owner_matchers_from_mappings(rows, display_names=[])
        # This used to become contains '5' and claim every VM with a 5 in its
        # name, hiding them from the Unmapped page while the SQL side — which
        # drops the rule — showed the customer nothing.
        for m in matchers:
            self.assertFalse(m.matches("srv-5-web"))

    def test_valid_rule_still_builds_a_matcher(self):
        rows = [{
            "data_source": "virtualization",
            "match_method": "prefix",
            "match_value": "Deneme",
            "crm_account_name": "Deneme",
        }]
        matchers = owner_matchers_from_mappings(rows, display_names=[])
        self.assertEqual(len(matchers), 1)
        self.assertTrue(matchers[0].matches("deneme-vm01"))


if __name__ == "__main__":
    unittest.main()
