"""The spreadsheet is the authority for the 27% of policies the naming standard
cannot disambiguate. Rows it cannot resolve are reported, never skipped in
silence — a silent skip looks identical to a successful seed.

Candidates are matched against the FULL CRM roster, never a pre-narrowed subset
(such as project customers only) — narrowing the pool before counting
candidates manufactures false single matches. 'Sabancı' resolves to 5 real CRM
accounts in production; only one of them carries a PRJ-* sales order. A lookup
scoped to project customers up front would find exactly that one and call it
resolved, when the honest answer is "ambiguous, ask a human." Project
membership is only allowed to decide whether an already-unambiguous match may
be WRITTEN (an alias on a non-project account is invisible on the Customer
Aliases admin page), never whether it's ambiguous in the first place.
"""
from unittest.mock import patch

from scripts.seed_backup_policy_aliases import (
    SeedPlan,
    apply_plan,
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
    """'Aksular' in the sheet is 'AKSULAR GIDA SANAYİ A.Ş.' in CRM, and that
    account carries a PRJ-* order, so it is both unambiguous and writable."""
    plan = resolve_accounts(
        [("Aksular", ["aksu", "aksular"])],
        [{"name": "AKSULAR GIDA SANAYİ A.Ş.", "accountid": "acc-aksu"}],
        project_account_ids={"acc-aksu"},
    )
    assert plan.matched == [("acc-aksu", "Aksular", "AKSULAR GIDA SANAYİ A.Ş.", ["aksu", "aksular"])]
    assert plan.not_found == []
    assert plan.ambiguous == []
    assert plan.not_addressable == []


def test_a_sheet_name_with_no_crm_account_is_reported_not_skipped():
    plan = resolve_accounts(
        [("Hayali Müşteri", ["haya"])],
        [{"name": "AKSULAR GIDA SANAYİ A.Ş.", "accountid": "acc-aksu"}],
        project_account_ids={"acc-aksu"},
    )
    assert plan.matched == []
    assert plan.not_found == ["Hayali Müşteri"]


def test_a_sheet_name_matching_two_crm_accounts_needs_a_human():
    plan = resolve_accounts(
        [("Avrora", ["avro", "avrora"])],
        [{"name": "AVRORA LLC", "accountid": "acc-1"},
         {"name": "AVRORA ENERJİ", "accountid": "acc-2"}],
        project_account_ids={"acc-1", "acc-2"},
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
        project_account_ids={"acc-1", "acc-2"},
    )
    report = format_report(plan)
    assert "Hayali Müşteri" in report
    assert "Avrora" in report
    assert "AVRORA LLC" in report


def test_report_names_matched_pairs_for_human_review():
    """A human must be able to eyeball sheet-name -> CRM-name pairs before
    approving --apply, not just a bare count — that is exactly what would have
    caught 'Sabancı' -> 'SABANCI DX' being printed with 4 other real
    candidates silently discarded."""
    plan = resolve_accounts(
        [("Aksular", ["aksu", "aksular"])],
        [{"name": "AKSULAR GIDA SANAYİ A.Ş.", "accountid": "acc-aksu"}],
        project_account_ids={"acc-aksu"},
    )
    report = format_report(plan)
    assert "Aksular" in report
    assert "AKSULAR GIDA SANAYİ A.Ş." in report


def test_false_single_match_becomes_ambiguous_not_matched():
    """The 'Sabancı' case verified in production: prefix-matches 5 full-roster
    accounts, but only one (SABANCI DX) carries a PRJ-* sales order. A lookup
    that filtered the candidate pool to project customers BEFORE matching
    would see only SABANCI DX and report a clean single match — this must
    instead report all 5 as ambiguous, deciding candidates on the full roster
    first."""
    roster = [
        {"name": "SABANCI ARF", "accountid": "acc-1"},
        {"name": "SABANCI DX", "accountid": "acc-2"},
        {"name": "SABANCI DİJİTAL TEKNOLOJİ A.Ş.", "accountid": "acc-3"},
        {"name": "SABANCI ÜNİVERSİTESİ", "accountid": "acc-4"},
        {"name": "SABANCIDX", "accountid": "acc-5"},
    ]
    plan = resolve_accounts(
        [("Sabancı", ["saban"])],
        roster,
        project_account_ids={"acc-2"},  # only SABANCI DX has a PRJ-* order
    )
    assert plan.matched == []
    assert len(plan.ambiguous) == 1
    assert plan.ambiguous[0][0] == "Sabancı"
    assert len(plan.ambiguous[0][1]) == 5


def test_not_addressable_when_the_only_full_roster_match_has_no_project_order():
    """AVRORA LLC exists in discovery_crm_accounts with zero sales orders. It is
    a real, unambiguous match — but writing an alias on it would be invisible
    on the Customer Aliases admin page, so it must be reported separately and
    never handed to apply_plan()."""
    plan = resolve_accounts(
        [("Avrora", ["avro", "avrora"])],
        [{"name": "AVRORA LLC", "accountid": "acc-1"}],
        project_account_ids=set(),  # acc-1 has no PRJ-* order
    )
    assert plan.matched == []
    assert plan.not_addressable == [("acc-1", "Avrora", "AVRORA LLC", ["avro", "avrora"])]


def test_report_names_not_addressable_rows():
    plan = resolve_accounts(
        [("Avrora", ["avro"])],
        [{"name": "AVRORA LLC", "accountid": "acc-1"}],
        project_account_ids=set(),
    )
    report = format_report(plan)
    assert "Avrora" in report
    assert "AVRORA LLC" in report


def test_apply_plan_writes_union_of_existing_and_new_mappings():
    """The save endpoint replaces an account's WHOLE mapping set, so apply_plan
    must send existing + new together, not just the new rule."""
    plan = SeedPlan(matched=[("acc-1", "Azer", "AZERSUN HOLDİNG MMC", ["azer"])])
    existing_alias = {
        "crm_accountid": "acc-1",
        "crm_account_name": "AZERSUN HOLDİNG MMC",
        "source_mappings": [
            {
                "data_source": "virtualization",
                "match_method": "contains",
                "match_value": "Azersun",
                "enabled": True,
            },
        ],
    }
    with patch("src.services.api_client.get_crm_aliases", return_value=[existing_alias]), \
         patch("src.services.api_client.put_crm_source_mappings") as mock_put:
        accounts_written, rules_added = apply_plan(plan)

    assert accounts_written == 1
    assert rules_added == 1
    mock_put.assert_called_once()
    _args, kwargs = mock_put.call_args
    written = kwargs["mappings"]
    assert any(m["data_source"] == "virtualization" and m["match_value"] == "Azersun" for m in written)
    assert any(m["data_source"] == "backup_netbackup" and m["match_value"] == "azer" for m in written)


def test_apply_plan_second_run_writes_nothing():
    """Idempotence: once the rule from the first run is already present, a
    second run must call put_crm_source_mappings zero times."""
    plan = SeedPlan(matched=[("acc-1", "Azer", "AZERSUN HOLDİNG MMC", ["azer"])])
    alias_after_first_run = {
        "crm_accountid": "acc-1",
        "crm_account_name": "AZERSUN HOLDİNG MMC",
        "source_mappings": [
            {
                "data_source": "backup_netbackup",
                "match_method": "prefix",
                "match_value": "azer",
                "enabled": True,
                "priority": 100,
                "notes": "backup-musteri-isim.xlsx seed",
            },
        ],
    }
    with patch("src.services.api_client.get_crm_aliases", return_value=[alias_after_first_run]), \
         patch("src.services.api_client.put_crm_source_mappings") as mock_put:
        accounts_written, rules_added = apply_plan(plan)

    assert accounts_written == 0
    assert rules_added == 0
    mock_put.assert_not_called()
