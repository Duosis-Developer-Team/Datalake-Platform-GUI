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
