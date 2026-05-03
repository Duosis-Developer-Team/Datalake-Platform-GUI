#!/usr/bin/env python3
"""Offline sanity checks for the unit-conversion graph used by SellableService.

Run from the repository root (or anywhere)::

    python shared/sellable/verify_units.py

The script never touches a database — it encodes the *same numeric
relationships* seeded in ``009_seed_unit_conversions.sql`` so operators
can quickly prove the GUI math still matches the migration after edits.

Optional datalake probe (best-effort)::

    set DATALAKE_DSN=postgresql://user:pass@host:5432/bulutlake
    python shared/sellable/verify_units.py --probe-nutanix-hz

This executes ``SELECT MAX(total_cpu_capacity) FROM nutanix_cluster_metrics``
and prints the raw magnitude so humans can decide whether the column is
Hz, MHz, or something else. psycopg2 must be installed for the probe.
"""
from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path
from typing import Iterable

# Allow ``python shared/sellable/verify_units.py`` (cwd-agnostic): repo root
# must precede this directory on sys.path so ``import shared`` resolves.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from shared.sellable.computation import convert_unit
from shared.sellable.models import UnitConversion


def _chain(value: float, chain: Iterable[UnitConversion]) -> float:
    v = float(value)
    for c in chain:
        v = convert_unit(v, c)
    return v


def _assert_close(name: str, got: float, want: float, *, tol: float = 1e-6) -> None:
    if not math.isclose(got, want, rel_tol=tol, abs_tol=tol):
        raise SystemExit(f"[FAIL] {name}: got {got!r} want {want!r}")


def verify_static_chain() -> None:
    """Hard-coded assertions mirroring the seed migration."""
    # Hz -> GHz -> vCPU (ceil)
    hz_to_ghz = UnitConversion("Hz", "GHz", 1e9, "divide", False)
    ghz_to_vcpu = UnitConversion("GHz", "vCPU", 8.0, "divide", True)
    _assert_close("2.5e9 Hz -> GHz", _chain(2_500_000_000, [hz_to_ghz]), 2.5)
    _assert_close("63.5 GHz -> vCPU ceil", _chain(63.5, [ghz_to_vcpu]), 8.0)

    bytes_to_gb = UnitConversion("bytes", "GB", float(1024 ** 3), "divide", False)
    _assert_close("1 GiB bytes -> GB", _chain(1024 ** 3, [bytes_to_gb]), 1.0)

    mb_to_gb = UnitConversion("MB", "GB", 1024.0, "divide", False)
    _assert_close("2048 MB -> GB", _chain(2048.0, [mb_to_gb]), 2.0)

    tb_to_gb = UnitConversion("TB", "GB", 1024.0, "multiply", False)
    _assert_close("1.5 TB -> GB", _chain(1.5, [tb_to_gb]), 1536.0)

    print("[OK] static conversion chain checks passed.")


def probe_nutanix_cpu_column() -> None:
    dsn = os.getenv("DATALAKE_DSN")
    if not dsn:
        print("[SKIP] DATALAKE_DSN not set — cannot probe nutanix_cluster_metrics.")
        return
    try:
        import psycopg2  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise SystemExit("[FAIL] psycopg2 required for --probe-nutanix-hz") from exc

    sql = "SELECT COALESCE(MAX(total_cpu_capacity), 0)::float FROM nutanix_cluster_metrics;"
    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            row = cur.fetchone()
    raw = float(row[0] or 0.0)
    print(f"[INFO] MAX(nutanix_cluster_metrics.total_cpu_capacity) = {raw:,.0f}")
    if raw == 0:
        print("[WARN] table empty — cannot infer units.")
        return
    for label, divisor in (("assume Hz", 1e9), ("assume MHz", 1e6), ("assume kHz", 1e3)):
        ghz = raw / divisor
        vcpu = convert_unit(ghz, UnitConversion("GHz", "vCPU", 8.0, "divide", True))
        print(f"       {label:12s} -> {ghz:,.3f} GHz -> {vcpu:,.0f} vCPU (ceil /8)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--probe-nutanix-hz",
        action="store_true",
        help="Optional datalake probe (needs DATALAKE_DSN + psycopg2).",
    )
    args = ap.parse_args(argv)

    verify_static_chain()
    if args.probe_nutanix_hz:
        probe_nutanix_cpu_column()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
