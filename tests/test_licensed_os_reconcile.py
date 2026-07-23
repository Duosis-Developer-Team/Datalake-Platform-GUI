from shared.licensing.reconcile import reconcile, FAMILY_TO_SOLD_CATEGORIES


def _sold(page_key, qty):
    return {"page_key": page_key, "entitled_qty": qty}


def test_windows_aggregates_multiple_categories():
    detected = {"rhel": 10, "suse": 2, "windows": 8, "free": 0, "unknown": 0}
    sold_rows = [
        _sold("license_redhat", 4),
        _sold("license_suse", 5),
        _sold("license_microsoft_spla", 6),
        _sold("license_microsoft_csp", 1),
        _sold("mgmt_os_windows", 1),
    ]
    rows = {r["family"]: r for r in reconcile(detected, sold_rows)}
    assert rows["rhel"]["detected"] == 10 and rows["rhel"]["sold"] == 4
    assert rows["rhel"]["delta"] == 6          # leakage
    assert rows["suse"]["sold"] == 5 and rows["suse"]["delta"] == -3
    assert rows["windows"]["sold"] == 8        # 6 + 1 + 1
    assert rows["windows"]["delta"] == 0


def test_zero_sold_shows_full_detected_as_delta():
    rows = {r["family"]: r for r in reconcile({"rhel": 3, "suse": 0, "windows": 0}, [])}
    assert rows["rhel"]["detected"] == 3
    assert rows["rhel"]["sold"] == 0
    assert rows["rhel"]["delta"] == 3


def test_only_licensed_families_returned():
    rows = reconcile({"rhel": 1, "free": 99, "unknown": 5}, [])
    assert {r["family"] for r in rows} == {"rhel", "suse", "windows"}


def test_map_covers_three_families():
    assert set(FAMILY_TO_SOLD_CATEGORIES) == {"rhel", "suse", "windows"}
