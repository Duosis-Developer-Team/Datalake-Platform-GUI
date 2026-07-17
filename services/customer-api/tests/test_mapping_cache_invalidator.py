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
    invalidate_for_accounts,
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
    deleted: list[str] = []

    def scan_keys(prefix):
        return [k for k in (KEYS if keys is None else keys) if k.startswith(prefix)]

    def delete_keys(batch):
        deleted.extend(batch)

    def default_resolver(name):
        return NAME_TO_ACCOUNT.get(name)

    return deleted, scan_keys, delete_keys, (resolver or default_resolver)


def test_deletes_every_name_belonging_to_the_account():
    deleted, scan_keys, delete_keys, resolver = _fakes()

    result = invalidate_for_accounts(
        {ACCT_A},
        resolve_account_id=resolver,
        scan_keys=scan_keys,
        delete_keys=delete_keys,
    )

    # Both display names of account A, primary and shadow alike.
    assert set(deleted) == {
        "customer_assets:cpu-usage-v3:Boyner:2026-07-09:2026-07-16",
        "customer_assets:cpu-usage-v3:Boyner:2026-07-09:2026-07-16:last_good",
        "customer_assets:cpu-usage-v3:BOYNER BÜYÜK MAĞAZACILIK A.Ş.:2026-07-10:2026-07-16",
    }
    assert result.deleted_count == 3
    assert set(result.matched_names) == {"Boyner", "BOYNER BÜYÜK MAĞAZACILIK A.Ş."}


def test_leaves_other_accounts_untouched():
    deleted, scan_keys, delete_keys, resolver = _fakes()

    invalidate_for_accounts(
        {ACCT_A},
        resolve_account_id=resolver,
        scan_keys=scan_keys,
        delete_keys=delete_keys,
    )

    assert not any("4A KOZMETİK" in k for k in deleted)


def test_shadow_is_deleted_with_its_primary():
    # A surviving :last_good shadow is exactly what makes a mapping change
    # invisible: cache_get falls back to it and the factory never re-runs.
    deleted, scan_keys, delete_keys, resolver = _fakes()

    invalidate_for_accounts(
        {ACCT_A},
        resolve_account_id=resolver,
        scan_keys=scan_keys,
        delete_keys=delete_keys,
    )

    assert "customer_assets:cpu-usage-v3:Boyner:2026-07-09:2026-07-16:last_good" in deleted


def test_unknown_name_is_skipped_not_fatal():
    keys = ["customer_assets:cpu-usage-v3:Ghost Corp:2026-07-09:2026-07-16"]
    deleted, scan_keys, delete_keys, resolver = _fakes(keys=keys)

    result = invalidate_for_accounts(
        {ACCT_A},
        resolve_account_id=resolver,
        scan_keys=scan_keys,
        delete_keys=delete_keys,
    )

    # Resolving to None is a clean answer: the read path would also find no
    # rules for it, so this account's mapping cannot affect that view.
    assert deleted == []
    assert result.deleted_count == 0


def test_resolver_failure_aborts_instead_of_skipping():
    def exploding_resolver(name):
        raise ResolutionError("webui pool down")

    deleted, scan_keys, delete_keys, _ = _fakes()

    with pytest.raises(ResolutionError):
        invalidate_for_accounts(
            {ACCT_A},
            resolve_account_id=exploding_resolver,
            scan_keys=scan_keys,
            delete_keys=delete_keys,
        )

    assert deleted == []


def test_resolves_each_distinct_name_once():
    calls: list[str] = []

    def counting_resolver(name):
        calls.append(name)
        return NAME_TO_ACCOUNT.get(name)

    _, scan_keys, delete_keys, _ = _fakes()

    invalidate_for_accounts(
        {ACCT_A},
        resolve_account_id=counting_resolver,
        scan_keys=scan_keys,
        delete_keys=delete_keys,
    )

    # "Boyner" appears in two keys but must cost one lookup.
    assert calls.count("Boyner") == 1


def test_no_matching_keys_reports_zero():
    deleted, scan_keys, delete_keys, resolver = _fakes(keys=["junk:key"])

    result = invalidate_for_accounts(
        {ACCT_A},
        resolve_account_id=resolver,
        scan_keys=scan_keys,
        delete_keys=delete_keys,
    )

    assert result.deleted_count == 0
    assert result.matched_names == ()


def test_scanned_count_reflects_keys_walked():
    deleted, scan_keys, delete_keys, resolver = _fakes()

    result = invalidate_for_accounts(
        {ACCT_A},
        resolve_account_id=resolver,
        scan_keys=scan_keys,
        delete_keys=delete_keys,
    )

    # scanned_count includes every key returned by scan_keys (filtered by prefix).
    # All customer_assets: prefixed keys in KEYS are walked.
    assert result.scanned_count == 4


def test_orphaned_shadow_is_deleted_even_without_its_primary():
    # Real state: on the live Redis, 5 of 8 shadows outlived their primary.
    # An orphaned shadow is what keeps a stale mapping alive, so it must go.
    keys = ["customer_assets:cpu-usage-v3:Boyner:2026-07-09:2026-07-16:last_good"]
    deleted, scan_keys, delete_keys, resolver = _fakes(keys=keys)

    result = invalidate_for_accounts(
        {ACCT_A},
        resolve_account_id=resolver,
        scan_keys=scan_keys,
        delete_keys=delete_keys,
    )

    assert deleted == keys
    assert result.deleted_count == 1
