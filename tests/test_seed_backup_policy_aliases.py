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
    group_matched_by_account,
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
    existing = [
        {
            "crm_accountid": "acc-1",
            "crm_account_name": "AZERSUN HOLDİNG MMC",
            "data_source": "virtualization",
            "match_method": "contains",
            "match_value": "Azersun",
            "enabled": True,
        },
    ]
    with patch("src.services.api_client.get_crm_account_source_mappings",
               return_value=existing), \
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
    after_first_run = [
        {
            "crm_accountid": "acc-1",
            "crm_account_name": "AZERSUN HOLDİNG MMC",
            "data_source": "backup_netbackup",
            "match_method": "prefix",
            "match_value": "azer",
            "enabled": True,
            "priority": 100,
            "notes": "backup-musteri-isim.xlsx seed",
        },
    ]
    with patch("src.services.api_client.get_crm_account_source_mappings",
               return_value=after_first_run), \
         patch("src.services.api_client.put_crm_source_mappings") as mock_put:
        accounts_written, rules_added = apply_plan(plan)

    assert accounts_written == 0
    assert rules_added == 0
    mock_put.assert_not_called()


def test_apply_plan_never_writes_ambiguous_or_not_addressable_rows():
    """apply_plan() must only ever act on plan.matched. Today that holds because
    the loop iterates plan.matched alone — but that guarantee is exactly the
    kind that quietly breaks when someone later "improves" the loop to also
    handle the other buckets. Writing a not_addressable row would create a
    mapping the Customer Aliases admin page cannot show (invisible orphan);
    writing an ambiguous row would attribute a policy to the wrong customer.
    Neither bucket should reach put_crm_source_mappings at all.
    """
    plan = SeedPlan(
        matched=[],
        ambiguous=[("Sabancı", ["SABANCI ARF", "SABANCI DX", "SABANCI ÜNİVERSİTESİ"])],
        not_addressable=[("acc-1", "Avrora", "AVRORA LLC", ["avro", "avrora"])],
    )
    with patch("src.services.api_client.get_crm_account_source_mappings", return_value=[]), \
         patch("src.services.api_client.put_crm_source_mappings") as mock_put:
        accounts_written, rules_added = apply_plan(plan)

    assert accounts_written == 0
    assert rules_added == 0
    mock_put.assert_not_called()


def test_two_sheet_rows_for_one_account_keep_both_token_sets():
    """apply_plan used to fetch every alias once and re-derive `mappings` from
    that one snapshot on each iteration, so two sheet rows resolving to the same
    accountid produced two PUTs — and the second, built from the pre-write
    snapshot, dropped the first's tokens. resolve_accounts()'s startswith
    fallback makes such duplicates easy to introduce ('Azer' and 'Azersun' both
    land on AZERSUN HOLDİNG)."""
    plan = SeedPlan(matched=[
        ("acc-1", "Azer", "AZERSUN HOLDİNG MMC", ["azer"]),
        ("acc-1", "Azersun", "AZERSUN HOLDİNG MMC", ["azersun", "azr"]),
    ])
    with patch("src.services.api_client.get_crm_account_source_mappings", return_value=[]), \
         patch("src.services.api_client.put_crm_source_mappings") as mock_put:
        accounts_written, rules_added = apply_plan(plan)

    # One account, one write — not two racing ones.
    assert accounts_written == 1
    assert rules_added == 3
    mock_put.assert_called_once()
    written = {m["match_value"] for m in mock_put.call_args.kwargs["mappings"]}
    assert written == {"azer", "azersun", "azr"}


def test_grouping_by_account_dedupes_repeated_tokens():
    grouped = group_matched_by_account([
        ("acc-1", "Azer", "AZERSUN HOLDİNG MMC", ["azer"]),
        ("acc-1", "Azer (2)", "AZERSUN HOLDİNG MMC", ["azer", "azr"]),
        ("acc-2", "Aksular", "AKSULAR GIDA", ["aksu"]),
    ])
    assert grouped == {
        "acc-1": ("AZERSUN HOLDİNG MMC", ["azer", "azr"]),
        "acc-2": ("AKSULAR GIDA", ["aksu"]),
    }


def test_apply_plan_reads_each_account_separately_not_one_alias_snapshot():
    """The read that feeds the write must be per-account and uncached.
    get_crm_aliases() is both project-scoped and cached for 300s behind an SWR
    TTL, and cache_service defaults to a per-process backend — so a snapshot
    taken there can be stale in exactly the worker that is about to overwrite
    it."""
    plan = SeedPlan(matched=[
        ("acc-1", "Azer", "AZERSUN HOLDİNG MMC", ["azer"]),
        ("acc-2", "Aksular", "AKSULAR GIDA", ["aksu"]),
    ])
    with patch("src.services.api_client.get_crm_account_source_mappings",
               return_value=[]) as mock_read, \
         patch("src.services.api_client.get_crm_aliases") as mock_aliases, \
         patch("src.services.api_client.put_crm_source_mappings"):
        apply_plan(plan)

    assert [c.args[0] for c in mock_read.call_args_list] == ["acc-1", "acc-2"]
    mock_aliases.assert_not_called()
