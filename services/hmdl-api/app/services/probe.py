"""Probe verdict semantics: which product a script belongs to, and who owns a failure."""

from __future__ import annotations

# `reason` is written by the probe runner from catalog heuristics. Grouping it by
# owner is what makes the screen actionable: a missing script is a NiFi deployment
# job, a 403 is a credentials job, a timeout is a network job.
_CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("script_missing", ("script_missing",)),
    # `build_argv:... username/password missing` is a credentials job, not a runner bug,
    # so the password needle has to win before the generic build_argv rule below.
    (
        "auth",
        ("auth_failed", "403", "forbidden", "hata:", "credentials", "password", "unauthorized"),
    ),
    ("network", ("network_unreachable", "network_timeout", "connection refused")),
    ("timeout", ("timeout",)),
    ("no_data", ("missing_stdout_signal", "missing_stderr_signal", "stdout_too_small")),
    ("runner", ("batch_parse", "build_argv", "ssh")),
)

PRODUCT_BY_COLLECTOR = {
    "vmware": "vmware",
    "nutanix": "nutanix",
    "acropolis": "nutanix",
    "ibm-hmc": "ibm",
    "veeam": "backup",
    "netbackup": "backup",
    "zerto": "backup",
}


def probe_product(collector_type: str) -> str:
    key = (collector_type or "").strip().lower()
    return PRODUCT_BY_COLLECTOR.get(key, "other")


def reason_category(reason: str, success: bool) -> str:
    if success:
        return "ok"
    text = (reason or "").lower()
    if not text:
        return "other"
    for category, needles in _CATEGORY_RULES:
        if any(n in text for n in needles):
            return category
    return "other"


def script_status(ok: int, total: int) -> str:
    if total <= 0:
        return "unknown"
    if ok == total:
        return "ok"
    if ok == 0:
        return "fail"
    return "partial"
