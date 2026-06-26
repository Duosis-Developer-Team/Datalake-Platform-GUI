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
    "storage_s3",
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


def _load_crm_engine_url(host: str | None) -> str:
    cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    if host:
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


def _fetch_s3_sellable(base_url: str) -> list[dict]:
    with httpx.Client(base_url=base_url, timeout=120.0) as client:
        resp = client.get(
            "/api/v1/crm/sellable-potential/by-panel",
            params={"dc_code": "*", "family": "storage_s3", "force_recompute": "true"},
        )
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []


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
        print(
            f"  {key}: panels={fam.get('panel_count')} "
            f"has_infra={fam.get('has_infra')} label={fam.get('family_label')}"
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
    payload = _fetch_overview(base, force_recompute=args.force_recompute)
    excerpt = {key: _panel_row(payload, key) for key in PANEL_KEYS}
    summary = payload.get("summary") or {}

    print(f"crm_engine={base}")
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

    for key, row in excerpt.items():
        if row is None:
            print(f"{key}: MISSING")
            continue
        print(
            f"{key}: total={row.get('total')} crm_sold={row.get('crm_sold_qty')} "
            f"used={row.get('used_qty')} sellable={row.get('sellable_qty')} "
            f"has_infra={row.get('has_infra_source')} binding={row.get('infra_binding')} "
            f"status={row.get('status')} quality={row.get('data_quality')} "
            f"reason={row.get('suspect_reason')}"
        )
        if key == "backup_netbackup_storage":
            crm = float(row.get("crm_sold_qty") or 0)
            total = float(row.get("total") or 0)
            if total > 0 and crm > total * 1.05:
                print("  WARN: CRM sold still exceeds total (>5%) — check unit mapping")
            prepared = _try_prepare_service_row(row)
            if prepared:
                print(
                    "  fmt: crm_sold=", prepared.get("crm_sold_fmt", "").replace("\n", " / "),
                    "| total=", prepared.get("total_fmt"),
                    "| used=", prepared.get("used_fmt", "").replace("\n", " / "),
                )
        if key == "storage_s3":
            if not row.get("has_infra_source"):
                print("  WARN: merged S3 row has no infra — check site-scoped sellable panels")
            elif float(row.get("total") or 0) <= 0:
                print("  WARN: merged S3 total is zero")

    print("sellable storage_s3 family:")
    try:
        sell_panels = _fetch_s3_sellable(base)
        for panel in sell_panels:
            print(
                f"  {panel.get('panel_key')}: total={panel.get('total')} "
                f"has_infra={panel.get('has_infra_source')}"
            )
    except Exception as exc:  # noqa: BLE001
        print(f"  sellable fetch failed: {exc}")

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
