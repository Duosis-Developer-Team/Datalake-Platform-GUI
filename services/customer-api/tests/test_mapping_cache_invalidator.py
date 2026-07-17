import pytest

from app.services.mapping_cache_invalidator import parse_customer_assets_key


@pytest.mark.parametrize(
    "key,version,name,is_shadow",
    [
        (
            "customer_assets:cpu-usage-v3:Boyner:2026-07-09:2026-07-16",
            "cpu-usage-v3",
            "Boyner",
            False,
        ),
        (
            "customer_assets:cpu-usage-v3:Boyner:2026-07-09:2026-07-16:last_good",
            "cpu-usage-v3",
            "Boyner",
            True,
        ),
        # Version token must not be pinned: a bump is already in flight.
        (
            "customer_assets:netbackup-policy-v4:Boyner:2026-07-09:2026-07-16",
            "netbackup-policy-v4",
            "Boyner",
            False,
        ),
        # Spaces, dots, Turkish characters.
        (
            "customer_assets:cpu-usage-v3:BOYNER BÜYÜK MAĞAZACILIK A.Ş.:2026-07-10:2026-07-16",
            "cpu-usage-v3",
            "BOYNER BÜYÜK MAĞAZACILIK A.Ş.",
            False,
        ),
        # 1h preset: timestamps contain colons, so split(":") cannot work here.
        (
            "customer_assets:cpu-usage-v3:Boyner:2026-07-16T13:54:18Z:2026-07-16T14:54:18Z",
            "cpu-usage-v3",
            "Boyner",
            False,
        ),
        # Name itself contains colons.
        (
            "customer_assets:cpu-usage-v3:Weird:Name:2026-07-09:2026-07-16",
            "cpu-usage-v3",
            "Weird:Name",
            False,
        ),
    ],
)
def test_parses_real_key_shapes(key, version, name, is_shadow):
    parsed = parse_customer_assets_key(key)
    assert parsed is not None
    assert parsed.version == version
    assert parsed.name == name
    assert parsed.is_shadow is is_shadow


def test_captures_date_bounds():
    parsed = parse_customer_assets_key(
        "customer_assets:cpu-usage-v3:Boyner:2026-07-09:2026-07-16"
    )
    assert parsed.start == "2026-07-09"
    assert parsed.end == "2026-07-16"


@pytest.mark.parametrize(
    "key",
    [
        "unmapped_resources:2026-07-09:2026-07-16",
        "customer_assets:cpu-usage-v3:Boyner:not-a-date:2026-07-16",
        "api:customer_resources:cpu-usage-v3:Boyner:x",
        "customer_assets:cpu-usage-v3:Boyner",
        "",
    ],
)
def test_rejects_foreign_keys(key):
    assert parse_customer_assets_key(key) is None


from app.services.mapping_cache_invalidator import (
    ResolutionError,
    plan_invalidation_for_accounts,
    plan_invalidation_for_every_name,
)

ACCT_A = "aaaa-1111"
ACCT_B = "bbbb-2222"

# One account, two display names — this is real: "Boyner" (hardcoded pilot name)
# and the CRM legal name both hold live cache entries for the same account.
NAME_TO_ACCOUNT = {
    "Boyner": ACCT_A,
    "BOYNER BÜYÜK MAĞAZACILIK A.Ş.": ACCT_A,
    "4A KOZMETİK SANAYİ VE TİCARET ANONİM ŞİRKETİ": ACCT_B,
}

KEYS = [
    "customer_assets:cpu-usage-v3:Boyner:2026-07-09:2026-07-16",
    "customer_assets:cpu-usage-v3:Boyner:2026-07-09:2026-07-16:last_good",
    "customer_assets:cpu-usage-v3:BOYNER BÜYÜK MAĞAZACILIK A.Ş.:2026-07-10:2026-07-16",
    "customer_assets:cpu-usage-v3:4A KOZMETİK SANAYİ VE TİCARET ANONİM ŞİRKETİ:2026-07-09:2026-07-16",
    "some_other_namespace:junk",
]


def _fakes(keys=None, resolver=None):
    def scan_keys(prefix):
        return [k for k in (KEYS if keys is None else keys) if k.startswith(prefix)]

    def default_resolver(name):
        return NAME_TO_ACCOUNT.get(name)

    return scan_keys, (resolver or default_resolver)


def test_dooms_every_name_belonging_to_the_account():
    scan_keys, resolver = _fakes()

    plan = plan_invalidation_for_accounts(
        {ACCT_A},
        resolve_account_id=resolver,
        scan_keys=scan_keys,
    )

    # Both display names of account A, primary and shadow alike.
    assert set(plan.doomed_keys) == {
        "customer_assets:cpu-usage-v3:Boyner:2026-07-09:2026-07-16",
        "customer_assets:cpu-usage-v3:Boyner:2026-07-09:2026-07-16:last_good",
        "customer_assets:cpu-usage-v3:BOYNER BÜYÜK MAĞAZACILIK A.Ş.:2026-07-10:2026-07-16",
    }
    assert len(plan.doomed_keys) == 3
    assert set(plan.matched_names) == {"Boyner", "BOYNER BÜYÜK MAĞAZACILIK A.Ş."}


def test_leaves_other_accounts_untouched():
    scan_keys, resolver = _fakes()

    plan = plan_invalidation_for_accounts(
        {ACCT_A},
        resolve_account_id=resolver,
        scan_keys=scan_keys,
    )

    assert not any("4A KOZMETİK" in k for k in plan.doomed_keys)


def test_shadow_is_doomed_with_its_primary():
    # A surviving :last_good shadow is exactly what makes a mapping change
    # invisible: cache_get falls back to it and the factory never re-runs.
    scan_keys, resolver = _fakes()

    plan = plan_invalidation_for_accounts(
        {ACCT_A},
        resolve_account_id=resolver,
        scan_keys=scan_keys,
    )

    assert "customer_assets:cpu-usage-v3:Boyner:2026-07-09:2026-07-16:last_good" in plan.doomed_keys


def test_unknown_name_is_skipped_not_fatal():
    keys = ["customer_assets:cpu-usage-v3:Ghost Corp:2026-07-09:2026-07-16"]
    scan_keys, resolver = _fakes(keys=keys)

    plan = plan_invalidation_for_accounts(
        {ACCT_A},
        resolve_account_id=resolver,
        scan_keys=scan_keys,
    )

    # Resolving to None is a clean answer: the read path would also find no
    # rules for it, so this account's mapping cannot affect that view.
    assert plan.doomed_keys == ()


def test_resolver_failure_aborts_instead_of_skipping():
    # "Cannot tell" must not degrade into "belongs to nobody": a swallowed
    # failure would silently skip keys and leave them stale.
    def exploding_resolver(name):
        raise ResolutionError("webui pool down")

    scan_keys, _ = _fakes()

    with pytest.raises(ResolutionError):
        plan_invalidation_for_accounts(
            {ACCT_A},
            resolve_account_id=exploding_resolver,
            scan_keys=scan_keys,
        )


def test_resolves_each_distinct_name_once():
    calls: list[str] = []

    def counting_resolver(name):
        calls.append(name)
        return NAME_TO_ACCOUNT.get(name)

    scan_keys, _ = _fakes()

    plan_invalidation_for_accounts(
        {ACCT_A},
        resolve_account_id=counting_resolver,
        scan_keys=scan_keys,
    )

    # "Boyner" appears in two keys but must cost one lookup.
    assert calls.count("Boyner") == 1


def test_no_matching_keys_reports_zero():
    scan_keys, resolver = _fakes(keys=["junk:key"])

    plan = plan_invalidation_for_accounts(
        {ACCT_A},
        resolve_account_id=resolver,
        scan_keys=scan_keys,
    )

    assert len(plan.doomed_keys) == 0
    assert plan.matched_names == ()


def test_scanned_count_reflects_keys_walked():
    scan_keys, resolver = _fakes()

    plan = plan_invalidation_for_accounts(
        {ACCT_A},
        resolve_account_id=resolver,
        scan_keys=scan_keys,
    )

    # scanned_count includes every key returned by scan_keys (filtered by prefix).
    # All customer_assets: prefixed keys in KEYS are walked.
    assert plan.scanned_count == 4


def test_orphaned_shadow_is_doomed_even_without_its_primary():
    # Real state: on the live Redis, 5 of 8 shadows outlived their primary.
    # An orphaned shadow is what keeps a stale mapping alive, so it must go.
    keys = ["customer_assets:cpu-usage-v3:Boyner:2026-07-09:2026-07-16:last_good"]
    scan_keys, resolver = _fakes(keys=keys)

    plan = plan_invalidation_for_accounts(
        {ACCT_A},
        resolve_account_id=resolver,
        scan_keys=scan_keys,
    )

    assert list(plan.doomed_keys) == keys
    assert len(plan.doomed_keys) == 1


# ---------------------------------------------------------------------------
# plan_invalidation_for_every_name — the resolver-free bulk planner
# ---------------------------------------------------------------------------


def test_every_name_planner_dooms_all_customer_assets_keys():
    scan_keys, _ = _fakes()

    plan = plan_invalidation_for_every_name(scan_keys=scan_keys)

    # Every customer_assets key, both accounts, primary and shadow alike.
    assert set(plan.doomed_keys) == set(KEYS[:4])
    assert set(plan.matched_names) == {
        "Boyner",
        "BOYNER BÜYÜK MAĞAZACILIK A.Ş.",
        "4A KOZMETİK SANAYİ VE TİCARET ANONİM ŞİRKETİ",
    }


def test_every_name_planner_ignores_foreign_keys():
    scan_keys, _ = _fakes()

    plan = plan_invalidation_for_every_name(scan_keys=scan_keys)

    # Only parseable customer_assets keys are touched; the scan prefix is
    # shared, so anything else in the namespace must be left alone.
    assert "some_other_namespace:junk" not in plan.doomed_keys
    assert plan.scanned_count == 4


def test_every_name_planner_dooms_a_name_that_resolves_to_nobody():
    """The whole point of the bulk planner. resync rewrites the very
    crm_account_name values the resolver matches on, so a name can stop
    resolving across it. The targeted planner would read that None as "belongs
    to nobody", skip the key, and leave it stale (see
    test_unknown_name_is_skipped_not_fatal — correct there, fatal here). With no
    resolver in the loop there is no None to misread."""
    unresolvable = "customer_assets:cpu-usage-v3:Renamed Away Co:2026-07-09:2026-07-16"
    keys = KEYS + [unresolvable]
    scan_keys, resolver = _fakes(keys=keys)

    # Proof the name is genuinely unresolvable: the targeted planner skips it.
    targeted = plan_invalidation_for_accounts(
        {ACCT_A}, resolve_account_id=resolver, scan_keys=scan_keys
    )
    assert unresolvable not in targeted.doomed_keys

    plan = plan_invalidation_for_every_name(scan_keys=scan_keys)

    assert unresolvable in plan.doomed_keys
    assert "Renamed Away Co" in plan.matched_names
