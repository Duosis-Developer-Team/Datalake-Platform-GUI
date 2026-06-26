#!/usr/bin/env python3
"""Verify CRM inventory NetBackup, S3, and virt family visibility on test/prod hosts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

GUI_ROOT = Path(__file__).resolve().parents[1]
CFG_PATH = GUI_ROOT.parent / ".cursor" / "local-environment.local.json"

PANEL_KEYS = (
    "backup_netbackup_storage",
    "storage_s3_ankara",
    "storage_s3_istanbul",
)

VIRT_FAMILIES = (
    "virt_classic",
    "virt_hyperconverged",
    "virt_power",
    "virt_power_hana",
)

EXPECTED_FAMILIES = (*VIRT_FAMILIES, "storage_s3", "backup_netbackup")
MERGED_S3_KEY = "storage_s3"


def _load_datacenter_api_url(host: str | None) -> str:
    cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    if host:
        urls = cfg.get("test_server", {}).get("urls", {})
        if host in ("10.134.52.250", "10.134.52.251"):
            key = "test_server" if host == "10.134.52.250" else "dc132_server"
            urls = cfg.get(key, {}).get("urls", urls)
        dc_url = urls.get("datacenter_api")
        if dc_url:
            return str(dc_url).rstrip("/")
        return f"http://{host}:8000"
    return cfg.get("test_server", {}).get("urls", {}).get(
        "datacenter_api",
        "http://10.134.52.250:8000",
    )


def _load_crm_engine_url(host: str | None) -> str:
    cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    if host:
        key = "test_server" if host == "10.134.52.250" else "dc132_server"
        urls = cfg.get(key, {}).get("urls", cfg.get("test_server", {}).get("urls", {}))
        crm_url = urls.get("crm_engine")
        if crm_url:
            return str(crm_url).rstrip("/")
        return f"http://{host}:8070"
    return cfg.get("test_server", {}).get("urls", {}).get(
        "crm_engine",
        "http://10.134.52.250:8070",
    )


def _fetch_overview(base_url: str, *, force_recompute: bool) -> dict:
    params: dict[str, str] = {"dc_code": "*"}
    if force_recompute:
        params["force_recompute"] = "true"
    with httpx.Client(base_url=base_url, timeout=300.0) as client:
        resp = client.get("/api/v1/crm/inventory-overview", params=params)
        resp.raise_for_status()
        return resp.json()


def _fetch_s3_pools(dc_api: str, dc_id: str) -> list[dict]:
    with httpx.Client(base_url=dc_api, timeout=120.0) as client:
        resp = client.get(f"/api/v1/datacenters/{dc_id}/s3/pools")
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else data.get("pools") or []


def _sum_s3_pools(pools: list[dict]) -> dict[str, float]:
    total = sum(float(p.get("total_usable") or p.get("total_usable_tb") or 0) for p in pools)
    used = sum(float(p.get("used") or p.get("used_tb") or 0) for p in pools)
    free = sum(float(p.get("free") or p.get("free_tb") or 0) for p in pools)
    if free <= 0 and total > 0:
        free = max(total - used, 0.0)
    return {"total": total, "used": used, "free": free}


def _pct_diff(a: float, b: float) -> float:
    if b == 0:
        return 0.0 if a == 0 else 100.0
    return abs(a - b) / abs(b) * 100.0


def _panel_row(payload: dict, key: str) -> dict | None:
    for row in payload.get("panels") or []:
        if row.get("panel_key") == key:
            return row
    return None


def _print_families(payload: dict) -> list[str]:
    print("families:")
    keys: list[str] = []
    for fam in payload.get("families") or []:
        key = str(fam.get("family") or "")
        keys.append(key)
        panel_keys = [p.get("panel_key") for p in (fam.get("panels") or [])]
        print(
            f"  {key}: panels={fam.get('panel_count')} "
            f"has_infra={fam.get('has_infra')} label={fam.get('family_label')} "
            f"keys={panel_keys}"
        )
    return keys


def _try_prepare_service_row(row: dict) -> dict | None:
    sys.path.insert(0, str(GUI_ROOT))
    try:
        from src.components.crm_inventory_report import prepare_service_row

        return prepare_service_row(row)
    except Exception as exc:  # noqa: BLE001
        print(f"  prepare_service_row skipped: {exc}")
        return None


def _sum_netbackup_pools(rows: list[dict]) -> dict[str, float]:
    tb = 1024.0 ** 4
    total = sum(float(r.get("usablesizebytes") or 0) for r in rows) / tb
    used = sum(float(r.get("usedcapacitybytes") or 0) for r in rows) / tb
    free = sum(float(r.get("availablespacebytes") or 0) for r in rows) / tb
    if free <= 0 and total > 0:
        free = max(total - used, 0.0)
    return {"total": total, "used": used, "free": free}


def _fetch_netbackup_pools(dc_api: str, dc_id: str) -> list[dict]:
    with httpx.Client(base_url=dc_api, timeout=120.0) as client:
        resp = client.get(
            f"/api/v1/datacenters/{dc_id}/backup/netbackup",
            params={"preset": "7d"},
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("rows") or []


def _check_netbackup_parity(
    inv_row: dict | None,
    dc_rows: list[dict],
    *,
    tolerance_pct: float = 5.0,
) -> None:
    if inv_row is None:
        print("  NetBackup inventory row MISSING")
        return
    dc = _sum_netbackup_pools(dc_rows)
    inv_total = float(inv_row.get("total") or 0)
    inv_used = float(inv_row.get("used_qty") or 0)
    inv_free = float(inv_row.get("free_qty") or 0)
    pre_dedup = float(inv_row.get("pre_dedup_qty") or 0)
    print(
        f"  DC13 pools: total={dc['total']:.2f} TB used={dc['used']:.2f} TB "
        f"free={dc['free']:.2f} TB (rows={len(dc_rows)})"
    )
    print(
        f"  global inventory: total={inv_total:.2f} used={inv_used:.2f} "
        f"free={inv_free:.2f} pre_dedup={pre_dedup:.2f}"
    )
    if inv_total < dc["total"] * 0.95:
        print("    WARN: global total below DC13 pool total — check pool aggregation")
    for metric, inv_val, dc_val in (
        ("used", inv_used, dc["used"]),
        ("free", inv_free, dc["free"]),
    ):
        diff = _pct_diff(inv_val, dc_val)
        status = "OK" if inv_val >= dc_val * 0.95 or diff <= tolerance_pct else "WARN"
        print(f"    {metric} global>=DC13: {status} (inv={inv_val:.2f} dc13={dc_val:.2f})")
    if inv_used < 100.0 and dc["used"] > 1000.0:
        print("    WARN: used still looks like jobs post-dedup, not pool used")
    if abs(inv_total - inv_used) < 1.0 and inv_total > 1000.0:
        print("    WARN: inventory total≈used — check column mapping or aggregation")
    if inv_total > 0 and inv_used > inv_total * 1.05:
        print("    WARN: inventory used exceeds total (>5%)")


def _check_s3_parity(
    label: str,
    inv_row: dict | None,
    dc_pools: list[dict],
    *,
    tolerance_pct: float = 1.0,
) -> None:
    if inv_row is None:
        print(f"  {label}: inventory row MISSING")
        return
    dc = _sum_s3_pools(dc_pools)
    inv_total = float(inv_row.get("total") or 0)
    inv_used = float(inv_row.get("used_qty") or 0)
    inv_free = float(inv_row.get("free_qty") or 0)
    print(
        f"  {label} inventory: total={inv_total:.2f} used={inv_used:.2f} "
        f"free={inv_free:.2f} mode={inv_row.get('inventory_free_mode')}"
    )
    print(
        f"  {label} DC pools: total={dc['total']:.2f} used={dc['used']:.2f} free={dc['free']:.2f}"
    )
    for metric, inv_val, dc_val in (
        ("total", inv_total, dc["total"]),
        ("used", inv_used, dc["used"]),
        ("free", inv_free, dc["free"]),
    ):
        diff = _pct_diff(inv_val, dc_val)
        status = "OK" if diff <= tolerance_pct else "WARN"
        print(f"    {metric} parity: {status} ({diff:.2f}% diff)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify inventory NetBackup/S3/virt rows")
    parser.add_argument("--host", help="Server host IP (default: test_server from local JSON)")
    parser.add_argument("--json-out", help="Write full excerpt JSON to path")
    parser.add_argument(
        "--force-recompute",
        action="store_true",
        help="Bypass crm-engine inventory Redis cache",
    )
    args = parser.parse_args()

    base = _load_crm_engine_url(args.host)
    dc_api = _load_datacenter_api_url(args.host)
    payload = _fetch_overview(base, force_recompute=args.force_recompute)
    excerpt = {key: _panel_row(payload, key) for key in PANEL_KEYS}
    summary = payload.get("summary") or {}

    print(f"crm_engine={base}")
    print(f"datacenter_api={dc_api}")
    print(
        f"panel_count={summary.get('panel_count')} "
        f"infra={summary.get('infra_panel_count')} "
        f"issues={summary.get('overage_panel_count')}+{summary.get('unsold_usage_count')}"
    )
    family_keys = _print_families(payload)
    missing_families = [f for f in EXPECTED_FAMILIES if f not in family_keys]
    if missing_families:
        print(f"WARN: missing families in grouped view: {missing_families}")
    else:
        print("OK: expected families present")

    merged = _panel_row(payload, MERGED_S3_KEY)
    if merged is None:
        print(f"OK: merged {MERGED_S3_KEY} row absent (un-merge expected)")
    else:
        print(f"WARN: merged {MERGED_S3_KEY} row still present — migration 024 may be pending")

    for key, row in excerpt.items():
        if row is None:
            print(f"{key}: MISSING")
            continue
        print(
            f"{key}: total={row.get('total')} crm_sold={row.get('crm_sold_qty')} "
            f"used={row.get('used_qty')} pre_dedup={row.get('pre_dedup_qty')} "
            f"savings={row.get('dedup_savings_qty')} ({row.get('dedup_savings_pct')}%) "
            f"free={row.get('free_qty')} free_tl={row.get('free_tl')} sellable={row.get('sellable_qty')} "
            f"free_mode={row.get('inventory_free_mode')} "
            f"has_infra={row.get('has_infra_source')} status={row.get('status')}"
        )
        if key == "backup_netbackup_storage":
            crm = float(row.get("crm_sold_qty") or 0)
            total = float(row.get("total") or 0)
            used = float(row.get("used_qty") or 0)
            if total > 0 and crm > total * 1.05:
                print("  WARN: CRM sold still exceeds total (>5%) — check unit mapping")
            if used > 0 and total > 0 and abs(used - total) < 1.0:
                print("  WARN: used≈total — likely column shift or wrong metric in Used")
            if used > total * 1.05:
                print("  WARN: used exceeds total (>5%) — check pool aggregation")
            prepared = _try_prepare_service_row(row)
            if prepared:
                used_fmt = prepared.get("used_fmt", "")
                total_fmt = prepared.get("total_fmt", "")
                print(
                    "  fmt: crm_sold=", prepared.get("crm_sold_fmt", "").replace("\n", " / "),
                    "| total=", total_fmt,
                    "| used=", used_fmt.replace("\n", " / "),
                    "| free=", prepared.get("free_fmt", "").replace("\n", " / "),
                )
                if total_fmt and total_fmt in used_fmt.split("\n")[0]:
                    print("  WARN: total value appears in used_fmt — column mapping bug")
        if key.startswith("storage_s3_"):
            if row.get("inventory_free_mode") != "physical":
                print("  WARN: S3 free_mode is not physical")
            if float(row.get("total") or 0) <= 0:
                print("  WARN: S3 site total is zero")

    print("S3 DC parity:")
    try:
        dc13 = _fetch_s3_pools(dc_api, "DC13")
        dc14 = _fetch_s3_pools(dc_api, "DC14")
        _check_s3_parity("Istanbul/DC13", excerpt.get("storage_s3_istanbul"), dc13)
        _check_s3_parity("Ankara/DC14", excerpt.get("storage_s3_ankara"), dc14)
    except Exception as exc:  # noqa: BLE001
        print(f"  S3 DC parity fetch failed: {exc}")

    print("NetBackup DC13 parity:")
    try:
        nb_rows = _fetch_netbackup_pools(dc_api, "DC13")
        _check_netbackup_parity(excerpt.get("backup_netbackup_storage"), nb_rows)
    except Exception as exc:  # noqa: BLE001
        print(f"  NetBackup DC parity fetch failed: {exc}")

    if args.json_out:
        out = {
            "summary": summary,
            "families": payload.get("families"),
            "panels": excerpt,
        }
        Path(args.json_out).write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
        print(f"wrote {args.json_out}")


if __name__ == "__main__":
    main()
