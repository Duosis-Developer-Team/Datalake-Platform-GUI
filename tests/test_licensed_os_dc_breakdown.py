"""DC-level licensed-OS breakdown by virtualization architecture."""
from __future__ import annotations

from shared.licensing.dc_breakdown import build_dc_breakdown

# (cluster, vmname, guest_os) — the shape VM_OS_BY_DC returns.
_VMS = [
    ("DC13-KM-CLS-NVME", "km-win-1", "Microsoft Windows Server 2022 (64-bit)"),
    ("DC13-KM-CLS-NVME", "km-win-2", "Microsoft Windows Server 2016 (64-bit)"),
    ("DC13-KM-CLS-NVME", "km-rhel-1", "Red Hat Enterprise Linux 9 (64-bit)"),
    ("DC13-G16-CLS-HYBRID", "hc-win-1", "Microsoft Windows Server 2019 (64-bit)"),
    ("DC13-G16-CLS-HYBRID", "hc-ubuntu", "Ubuntu Linux (64-bit)"),
    ("DC13-G16-CLS-HYBRID", "hc-other", "Other Linux (64-bit)"),
]

# (lparname, ostype) — the shape POWER_OS_BY_DC returns.
_LPARS = [
    ("acme-lpar1", "Linux - SUSE"),
    ("acme-lpar2", "Linux - SUSE"),
    ("acme-lpar3", "AIX"),
    ("acme-lpar4", "Unknown"),
]


def test_classic_and_hyperconverged_are_split_on_the_km_cluster_rule():
    out = build_dc_breakdown(_VMS, [], 0)
    classic = out["architectures"]["classic"]
    hyper = out["architectures"]["hyperconverged"]
    assert classic["instances"] == 3
    assert classic["families"]["windows"] == 2
    assert classic["families"]["rhel"] == 1
    assert hyper["instances"] == 3
    assert hyper["families"]["windows"] == 1
    assert hyper["families"]["free"] == 1      # Ubuntu
    assert hyper["families"]["unknown"] == 1   # "Other Linux" — not guessed at


def test_power_lpars_are_classified_from_the_hmc_ostype():
    power = build_dc_breakdown([], _LPARS, 0)["architectures"]["power"]
    assert power["instances"] == 4
    assert power["families"]["suse"] == 2
    # AIX and "Unknown" carry no resale licence family — they must not inflate one.
    assert power["families"]["windows"] == 0
    assert power["families"]["rhel"] == 0


def test_pure_nutanix_reports_a_blind_spot_not_a_zero():
    """1,483 of 1,531 AHV guests have no OS anywhere. Showing them as 'unknown'
    inside the tally would read as a classification result; they are missing data."""
    out = build_dc_breakdown(_VMS, [], 1483)
    ahv = out["architectures"]["pure_nutanix"]
    assert ahv["instances"] == 1483
    assert ahv["no_os_telemetry"] == 1483
    assert "families" not in ahv


def test_totals_sum_the_architectures_that_have_telemetry():
    out = build_dc_breakdown(_VMS, _LPARS, 1483)
    assert out["totals"]["families"]["windows"] == 3
    assert out["totals"]["families"]["rhel"] == 1
    assert out["totals"]["families"]["suse"] == 2
    assert out["totals"]["licensed"] == 6          # 3 win + 1 rhel + 2 suse
    assert out["totals"]["instances"] == 10        # 6 VMs + 4 LPARs, AHV excluded
    assert out["totals"]["no_os_telemetry"] == 1483


def test_empty_input_produces_a_zeroed_but_complete_shape():
    out = build_dc_breakdown([], [], 0)
    assert set(out["architectures"]) == {"classic", "hyperconverged", "pure_nutanix", "power"}
    assert out["totals"]["licensed"] == 0
    assert out["architectures"]["classic"]["families"]["windows"] == 0


def test_unclassified_os_strings_are_sampled_for_manual_review():
    """4,963 guests platform-wide carry an OS string the rule table does not
    recognise ("Other Linux (64-bit)", "Other (64-bit)"...). Surfacing samples is
    how the classifier gets extended; hiding them makes 'unknown' permanent."""
    out = build_dc_breakdown(_VMS, _LPARS, 0)
    samples = out["unknown_samples"]
    assert "Other Linux (64-bit)" in samples
    assert "Unknown" in samples          # from the Power ostype column
    # Classified guests must never appear.
    assert not any("Windows" in s for s in samples)


def test_unknown_samples_are_deduped_and_bounded():
    rows = [("DC13-G16-CLS", f"vm{i}", "Other Linux (64-bit)") for i in range(200)]
    rows += [("DC13-G16-CLS", f"x{i}", f"Weird OS {i}") for i in range(200)]
    samples = build_dc_breakdown(rows, [], 0)["unknown_samples"]
    assert samples.count("Other Linux (64-bit)") == 1
    assert len(samples) <= 50            # a review list, not a data dump


def test_guests_with_no_os_string_are_not_sampled():
    """A blank is missing telemetry, not an unrecognised string — nothing to review."""
    assert build_dc_breakdown([("c", "vm", None), ("c", "vm2", "  ")], [], 0)["unknown_samples"] == []


def test_rows_with_no_cluster_name_fall_to_hyperconverged():
    # Mirrors the billing split: anything not matching KM is hyperconverged.
    out = build_dc_breakdown([(None, "orphan", "Microsoft Windows Server 2022 (64-bit)")], [], 0)
    assert out["architectures"]["hyperconverged"]["families"]["windows"] == 1
    assert out["architectures"]["classic"]["instances"] == 0
