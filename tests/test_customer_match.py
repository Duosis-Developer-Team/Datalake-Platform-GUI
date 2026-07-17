"""Parity + behaviour tests for shared.customer.match (pure, no DB).

The parity test is the point of this file: it simulates Postgres ILIKE and
asserts sql_pattern() and predicate() agree for every method x value x name.
If someone ever changes one side only, this goes red.

All company names below are fictional placeholders; they exist only to exercise
the matching rules. No real customer data.
"""
import re
import unittest

from shared.customer import match


def ilike_matches(pattern: str, name: str) -> bool:
    """Simulate Postgres ILIKE with the default backslash escape character."""
    out: list[str] = []
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "\\" and i + 1 < len(pattern):
            out.append(re.escape(pattern[i + 1]))
            i += 2
            continue
        if ch == "%":
            out.append(".*")
        elif ch == "_":
            out.append(".")
        else:
            out.append(re.escape(ch))
        i += 1
    return re.fullmatch("".join(out), name, re.IGNORECASE | re.DOTALL) is not None


class TestIlikeSimulator(unittest.TestCase):
    """The simulator is the parity test's oracle, so it needs its own check."""

    def test_percent_is_a_wildcard(self):
        self.assertTrue(ilike_matches("%Boyner%", "xxBoyneryy"))

    def test_underscore_matches_exactly_one_char(self):
        self.assertTrue(ilike_matches("A_B", "AxB"))
        self.assertFalse(ilike_matches("A_B", "AxxB"))
        self.assertFalse(ilike_matches("A_B", "AB"))

    def test_escaped_wildcards_are_literal(self):
        self.assertTrue(ilike_matches(r"A\_B", "A_B"))
        self.assertFalse(ilike_matches(r"A\_B", "AxB"))
        self.assertTrue(ilike_matches(r"50\%", "50%"))
        self.assertFalse(ilike_matches(r"50\%", "50X"))

    def test_case_insensitive(self):
        self.assertTrue(ilike_matches("boyner", "BOYNER"))


class TestEscapeLike(unittest.TestCase):
    def test_escapes_wildcards_and_backslash(self):
        self.assertEqual(match.escape_like("Boyner_Dr"), r"Boyner\_Dr")
        self.assertEqual(match.escape_like("50%"), r"50\%")
        self.assertEqual(match.escape_like("a\\b"), r"a\\b")

    def test_empty_is_safe(self):
        self.assertEqual(match.escape_like(""), "")


class TestSqlPattern(unittest.TestCase):
    def test_four_text_methods(self):
        self.assertEqual(match.sql_pattern("contains", "Boyner"), ("ilike", "%Boyner%"))
        self.assertEqual(match.sql_pattern("prefix", "Boyner"), ("ilike", "Boyner%"))
        self.assertEqual(match.sql_pattern("suffix", "Boyner"), ("ilike", "%Boyner"))
        self.assertEqual(match.sql_pattern("exact", "Boyner"), ("ilike", "Boyner"))

    def test_exact_is_wildcard_free_ilike(self):
        kind, pattern = match.sql_pattern("exact", "Boyner_Dr")
        self.assertEqual(kind, "ilike")
        self.assertEqual(pattern, r"Boyner\_Dr")

    def test_underscore_is_escaped_in_every_text_method(self):
        for method in match.TEXT_METHODS:
            _kind, pattern = match.sql_pattern(method, "Boyner_Dr")
            self.assertIn(r"\_", pattern, f"{method} must escape underscore")

    def test_id_exact_passes_value_through(self):
        self.assertEqual(match.sql_pattern("id_exact", "5"), ("id_exact", "5"))

    def test_unknown_method_falls_back_to_contains(self):
        self.assertEqual(match.sql_pattern("bogus", "Boyner"), ("ilike", "%Boyner%"))

    def test_value_is_stripped(self):
        self.assertEqual(match.sql_pattern("exact", "  Boyner  "), ("ilike", "Boyner"))


class TestPredicate(unittest.TestCase):
    def test_four_text_methods(self):
        self.assertTrue(match.predicate("contains", "boyner")("xxBoynerxx"))
        self.assertTrue(match.predicate("prefix", "boyner")("Boyner-vm01"))
        self.assertTrue(match.predicate("suffix", "vm01")("Boyner-vm01"))
        self.assertTrue(match.predicate("exact", "boyner")("Boyner"))
        self.assertFalse(match.predicate("exact", "boyner")("Boyner-vm01"))

    def test_underscore_is_literal(self):
        p = match.predicate("contains", "Boyner_Dr")
        self.assertTrue(p("Boyner_Dr_Prod"))
        self.assertFalse(p("BoynerXDr"))

    def test_empty_value_never_matches(self):
        self.assertFalse(match.predicate("contains", "")("anything"))
        self.assertFalse(match.predicate("contains", "   ")("anything"))

    def test_id_exact_never_name_matches(self):
        # Mirrors SQL: an id_exact rule contributes no name pattern at all.
        self.assertFalse(match.predicate("id_exact", "5")("srv-5-web"))

    def test_name_is_not_stripped(self):
        # ILIKE compares the column as stored; stripping here would make exact
        # match a trailing-space name that SQL rejects.
        self.assertFalse(match.predicate("exact", "Boyner")("Boyner "))


class TestAllowedMethods(unittest.TestCase):
    def test_id_sources_only_allow_id_exact(self):
        for source in match.ID_SOURCES:
            self.assertEqual(match.allowed_methods(source), match.ID_METHODS)
            self.assertTrue(match.is_allowed(source, "id_exact"))
            self.assertFalse(match.is_allowed(source, "contains"))

    def test_name_sources_reject_id_exact(self):
        for source in ("virtualization", "netbox_vm_customer", "backup_veeam", "s3_icos"):
            self.assertEqual(match.allowed_methods(source), match.TEXT_METHODS)
            self.assertFalse(match.is_allowed(source, "id_exact"))
            self.assertTrue(match.is_allowed(source, "exact"))

    def test_normalize_method_repairs_bad_input(self):
        self.assertEqual(match.normalize_method("virtualization", "id_exact"), "contains")
        self.assertEqual(match.normalize_method("physical_device", "contains"), "id_exact")
        self.assertEqual(match.normalize_method("virtualization", "PREFIX"), "prefix")


class TestSqlPredicateParity(unittest.TestCase):
    """The guard: SQL and in-memory must agree, for every method and every name."""

    VALUES = ["Boyner", "Boyner_Dr", "boynerdr2_boynerdr2", "50%", "A_B", "back\\slash"]
    NAMES = [
        "Boyner", "boyner", "BOYNER",
        "Boyner_Dr", "BoynerXDr", "Boyner-Dr", "Boyner Dr",
        "Boyner_Dr_Prod", "prefix-Boyner_Dr", "50%", "50X", "A_B", "AxB",
        "boynerdr2_boynerdr2", "back\\slash", "unrelated-vm",
        # Whitespace: ILIKE compares the column as stored, so predicate() must
        # not strip the name either. These lock that in.
        "Boyner ", " Boyner", "",
    ]

    def test_parity(self):
        for method in match.ALL_METHODS:
            for value in self.VALUES:
                kind, pattern = match.sql_pattern(method, value)
                pred = match.predicate(method, value)
                for name in self.NAMES:
                    py = pred(name)
                    if kind == "id_exact":
                        sql = False  # id_exact contributes no name pattern
                    else:
                        sql = ilike_matches(pattern, name)
                    self.assertEqual(
                        sql, py,
                        f"divergence: method={method!r} value={value!r} name={name!r} "
                        f"pattern={pattern!r} sql={sql} python={py}",
                    )


if __name__ == "__main__":
    unittest.main()
