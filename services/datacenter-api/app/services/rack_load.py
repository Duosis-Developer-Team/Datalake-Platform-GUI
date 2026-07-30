# services/datacenter-api/app/services/rack_load.py
"""Per-rack workload from NetBox rack membership + hypervisor host metrics.

"Load" is the platform's existing (CPU/RAM utilisation) quantity pushed down to
rack level -- deliberately NOT called "health", which ADR-0027 already assigns to
data freshness / automation health.

A rack's load is the MAX over its monitored devices, never the average: one
saturated host among twenty idle ones is a rack you cannot place work in, and an
average hides exactly that. A rack whose devices have no metrics at all reports
load_pct=None (rendered "Not monitored"), never 0 -- zero reads as idle capacity.
"""
from __future__ import annotations

from typing import Any, Iterable, Sequence


def _pct(used: Any, capacity: Any) -> float | None:
    """used/capacity as a percentage, or None when used/capacity is absent/zero.

    A missing `used` reading (None, or not coercible to a float) means that
    counter did not report -- e.g. a collector outage on CPU while memory and
    capacity still report. That must surface as None ("unknown"), never as a
    numeric 0.0 ("idle") -- `used or 0` would silently coerce None to 0. A
    genuine 0 reading must still round-trip as 0.0, so the None check happens
    before any arithmetic.
    """
    if used is None:
        return None
    try:
        cap = float(capacity or 0)
        if cap <= 0:
            return None
        return round(float(used) / cap * 100, 1)
    except (TypeError, ValueError):
        return None


def build_metric_index(
    vmware_rows: Sequence[Sequence[Any]] = (),
    nutanix_rows: Sequence[Sequence[Any]] = (),
    ibm_rows: Sequence[Sequence[Any]] = (),
) -> dict[str, dict]:
    """{lower(host name) -> {cpu_pct, ram_pct, source}} from the three host families.

    Row shapes (all "latest per host", produced by queries/rack_load.py):
      vmware_rows:  (vmhost, cpu_used_ghz, cpu_cap_ghz, mem_used_gb, mem_cap_gb)
      nutanix_rows: (host_name, cpu_used_hz, cpu_cap_hz, mem_used_bytes, mem_cap_bytes)
      ibm_rows:     (server_name, proc_used, proc_total, mem_total, mem_available)

    Keys are lowercased because NetBox device names and hypervisor host names agree
    on spelling but not always on case -- the same lower(name) idiom
    shared/licensing/os_sql.py uses for the VM-side join.
    """
    index: dict[str, dict] = {}

    def _put(name: Any, cpu_pct: float | None, ram_pct: float | None, source: str) -> None:
        key = str(name or "").strip().lower()
        if not key:
            return
        index[key] = {"cpu_pct": cpu_pct, "ram_pct": ram_pct, "source": source}

    for r in vmware_rows or ():
        _put(r[0], _pct(r[1], r[2]), _pct(r[3], r[4]), "vmware")
    for r in nutanix_rows or ():
        _put(r[0], _pct(r[1], r[2]), _pct(r[3], r[4]), "nutanix")
    for r in ibm_rows or ():
        # IBM reports AVAILABLE memory, not used -- used = total - available.
        total_mem = float(r[3] or 0)
        available = float(r[4] or 0)
        _put(r[0], _pct(r[1], r[2]), _pct(total_mem - available, total_mem), "ibm")

    return index


def aggregate_rack_load(
    device_rows: Iterable[Sequence[Any]],
    metric_index: dict[str, dict],
) -> list[dict]:
    """(rack_name, device_name) rows + metric index -> one load dict per rack.

    Every rack that has devices appears in the output, including racks where
    nothing is monitored -- the caller needs to tell "no metrics" apart from
    "rack absent from this DC".
    """
    racks: dict[str, dict] = {}

    for row in device_rows or ():
        rack_name = str(row[0] or "").strip()
        device_name = str(row[1] or "").strip()
        if not rack_name:
            continue
        entry = racks.setdefault(rack_name, {
            "rack_name": rack_name, "load_pct": None, "cpu_pct": None,
            "ram_pct": None, "monitored_devices": 0, "total_devices": 0,
            "hottest_device": None,
        })
        entry["total_devices"] += 1

        metrics = metric_index.get(device_name.lower()) if device_name else None
        if not metrics:
            continue
        cpu, ram = metrics.get("cpu_pct"), metrics.get("ram_pct")
        candidates = [v for v in (cpu, ram) if v is not None]
        if not candidates:
            continue

        entry["monitored_devices"] += 1
        device_load = max(candidates)
        if entry["load_pct"] is None or device_load > entry["load_pct"]:
            entry["load_pct"] = device_load
            entry["cpu_pct"] = cpu
            entry["ram_pct"] = ram
            entry["hottest_device"] = device_name

    return [racks[k] for k in sorted(racks)]
