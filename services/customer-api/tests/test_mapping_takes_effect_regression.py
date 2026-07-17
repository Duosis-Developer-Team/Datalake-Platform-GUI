from unittest.mock import MagicMock, patch

from app.services.customer_service import CustomerService

ACCOUNT = "acct-boyner"

# Mirrors production: one account cached under two display names, primary and
# shadow, exactly as observed on the live Redis.
SEEDED_KEYS = [
    "customer_assets:cpu-usage-v3:Boyner:2026-07-09:2026-07-16",
    "customer_assets:cpu-usage-v3:Boyner:2026-07-09:2026-07-16:last_good",
    "customer_assets:cpu-usage-v3:BOYNER BÜYÜK MAĞAZACILIK A.Ş.:2026-07-09:2026-07-16",
    "customer_assets:cpu-usage-v3:BOYNER BÜYÜK MAĞAZACILIK A.Ş.:2026-07-09:2026-07-16:last_good",
    "customer_assets:cpu-usage-v3:Other Corp:2026-07-09:2026-07-16",
]


def test_saving_a_mapping_evicts_every_cached_view_of_that_account():
    store = {k: {"stale": True} for k in SEEDED_KEYS}
    svc = CustomerService.__new__(CustomerService)
    svc._webui = MagicMock()

    def fake_resolve(name):
        return ACCOUNT if name.lower().startswith("boyner") else "other-acct"

    with patch("app.services.customer_service.cache") as cache, patch.object(
        CustomerService, "resolve_account_id_strict", side_effect=fake_resolve
    ), patch.object(CustomerService, "_schedule_mapping_warm"):
        cache.scan_prefix.side_effect = lambda p: [k for k in store if k.startswith(p)]
        cache.delete.side_effect = store.pop

        warning = svc.invalidate_mapping_caches({ACCOUNT})

    assert warning is None
    # Both display names gone, primary AND shadow.
    assert not [k for k in store if "Boyner" in k or "BOYNER" in k]
    # The unrelated account is untouched.
    assert "customer_assets:cpu-usage-v3:Other Corp:2026-07-09:2026-07-16" in store


def test_the_last_good_shadow_is_not_left_behind():
    # A surviving shadow is what made the mapping invisible for ~24h: cache_get
    # falls back to it, so run_singleflight never calls the factory.
    store = {k: {"stale": True} for k in SEEDED_KEYS}
    svc = CustomerService.__new__(CustomerService)
    svc._webui = MagicMock()

    with patch("app.services.customer_service.cache") as cache, patch.object(
        CustomerService, "resolve_account_id_strict", return_value=ACCOUNT
    ), patch.object(CustomerService, "_schedule_mapping_warm"):
        cache.scan_prefix.side_effect = lambda p: [k for k in store if k.startswith(p)]
        cache.delete.side_effect = store.pop

        svc.invalidate_mapping_caches({ACCOUNT})

    assert not [k for k in store if k.endswith(":last_good")]
