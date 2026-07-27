"""The spreadsheet is the authority for the 27% of policies the naming standard
cannot disambiguate. Rows it cannot resolve are reported, never skipped in
silence — a silent skip looks identical to a successful seed.
"""
from scripts.seed_backup_policy_aliases import (
    format_report,
    parse_sheet_rows,
    resolve_accounts,
)


def test_multi_token_cells_split_into_separate_rows():
    rows = parse_sheet_rows([
        ("Aksular", "aksu,aksular"),
        ("Alisan lojistik", "alis, alis-logo"),
        ("Azer", "azer"),
    ])
    assert dict(rows) == {
        "Aksular": ["aksu", "aksular"],
        "Alisan lojistik": ["alis", "alis-logo"],
        "Azer": ["azer"],
    }


def test_blank_and_header_rows_are_ignored():
    rows = parse_sheet_rows([
        ("MÜŞTERİ ADI", "POLICY ADI"),
        ("", ""),
        (None, None),
        ("Azer", "azer"),
    ])
    assert dict(rows) == {"Azer": ["azer"]}


def test_short_sheet_names_resolve_to_full_legal_crm_names():
    """'Aksular' in the sheet is 'AKSULAR GIDA SANAYİ A.Ş.' in CRM."""
    plan = resolve_accounts(
        [("Aksular", ["aksu", "aksular"])],
        [{"name": "AKSULAR GIDA SANAYİ A.Ş.", "accountid": "acc-aksu"}],
    )
    assert plan.matched == [("acc-aksu", "AKSULAR GIDA SANAYİ A.Ş.", ["aksu", "aksular"])]
    assert plan.not_found == []
    assert plan.ambiguous == []


def test_a_sheet_name_with_no_crm_account_is_reported_not_skipped():
    plan = resolve_accounts(
        [("Hayali Müşteri", ["haya"])],
        [{"name": "AKSULAR GIDA SANAYİ A.Ş.", "accountid": "acc-aksu"}],
    )
    assert plan.matched == []
    assert plan.not_found == ["Hayali Müşteri"]


def test_a_sheet_name_matching_two_crm_accounts_needs_a_human():
    plan = resolve_accounts(
        [("Avrora", ["avro", "avrora"])],
        [{"name": "AVRORA LLC", "accountid": "acc-1"},
         {"name": "AVRORA ENERJİ", "accountid": "acc-2"}],
    )
    assert plan.matched == []
    assert len(plan.ambiguous) == 1
    assert plan.ambiguous[0][0] == "Avrora"
    assert sorted(plan.ambiguous[0][1]) == ["AVRORA ENERJİ", "AVRORA LLC"]


def test_report_names_every_unresolved_row():
    plan = resolve_accounts(
        [("Hayali Müşteri", ["haya"]), ("Avrora", ["avro"])],
        [{"name": "AVRORA LLC", "accountid": "acc-1"},
         {"name": "AVRORA ENERJİ", "accountid": "acc-2"}],
    )
    report = format_report(plan)
    assert "Hayali Müşteri" in report
    assert "Avrora" in report
    assert "AVRORA LLC" in report
