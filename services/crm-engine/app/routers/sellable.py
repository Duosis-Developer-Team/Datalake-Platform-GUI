"""Sellable Potential REST endpoints (crm-engine).

Routes:
    GET  /crm/sellable-potential/summary?dc_code=*           -> DashboardSummary
    GET  /crm/sellable-potential/by-panel?dc_code=*&family=  -> list[PanelResult]
    GET  /crm/sellable-potential/by-family?dc_code=*         -> list[FamilyAggregate]

    GET  /crm/metric-tags?prefix=...&scope_type=&scope_id=   -> dict[key->value]
    GET  /crm/metric-tags/snapshots?metric_key=...&hours=720 -> trend points

    GET  /crm/panels                                          -> list[PanelDef]
    PUT  /crm/panels/{panel_key}                              -> upsert PanelDef
    GET  /crm/panels/{panel_key}/infra-source?dc_code=*       -> InfraSource
    PUT  /crm/panels/{panel_key}/infra-source                 -> upsert per dc

    GET  /crm/resource-ratios                                 -> list per family/dc
    PUT  /crm/resource-ratios/{family}                        -> upsert (with optional dc_code)

    GET  /crm/unit-conversions
    PUT  /crm/unit-conversions/{from_unit}/{to_unit}
    DELETE /crm/unit-conversions/{from_unit}/{to_unit}
"""
from __future__ import annotations

from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.db.queries import sellable as sq
from app.models.schemas import (
    MetricSnapshotRow,
    MetricValueRow,
    PanelDefinitionRow,
    PanelDefinitionUpsert,
    PanelInfraSourceRow,
    PanelInfraSourceUpsert,
    ResourceRatioRow,
    ResourceRatioUpsert,
    UnitConversionRow,
    UnitConversionUpsert,
)
from app.services.sellable_service import SellableService
from app.services.webui_db import WebuiPool

router = APIRouter()


def _sellable(request: Request) -> SellableService:
    svc: SellableService = getattr(request.app.state, "sellable", None)
    if svc is None or not svc.is_available:
        raise HTTPException(status_code=503, detail="SellableService not available")
    return svc


def _webui(request: Request) -> WebuiPool:
    webui: WebuiPool = request.app.state.webui
    if webui is None or not webui.is_available:
        raise HTTPException(status_code=503, detail="WebUI configuration DB not available")
    return webui


# ---------------------------------------------------------------------------
# Dashboard read endpoints
# ---------------------------------------------------------------------------


def _parse_clusters(raw: Optional[str]) -> Optional[list[str]]:
    """Parse a CSV ``clusters`` query param into a clean list. Empty/None → None."""
    if not raw:
        return None
    items = [c.strip() for c in raw.split(",")]
    items = [c for c in items if c]
    return items or None


@router.get("/crm/sellable-potential/summary", response_model=dict)
def get_summary(
    dc_code: str = "*",
    clusters: Optional[str] = Query(
        None,
        description="Optional CSV of cluster names. Restricts virt_classic / virt_hyperconverged "
                    "panel scope to those clusters by reading datacenter-api compute endpoint.",
    ),
    svc: SellableService = Depends(_sellable),
):
    return svc.compute_summary(
        dc_code=dc_code,
        selected_clusters=_parse_clusters(clusters),
    ).to_dict()


@router.get("/crm/sellable-potential/by-panel", response_model=List[dict])
def get_by_panel(
    dc_code: str = "*",
    family: Optional[str] = None,
    clusters: Optional[str] = Query(
        None,
        description="Optional CSV of cluster names. When provided, virt_classic / virt_hyperconverged "
                    "panels read total + allocated from datacenter-api /compute/{kind}?clusters=... "
                    "instead of the dc-wide datalake + Redis path.",
    ),
    svc: SellableService = Depends(_sellable),
):
    # Forward family to compute_all_panels so unrelated panels are not even
    # loaded — saves a full WebUI + datalake pass when the caller only wants
    # virt_classic (3 of ~70 panels).
    panels = svc.compute_all_panels(
        dc_code=dc_code,
        selected_clusters=_parse_clusters(clusters),
        family=family,
    )
    return [p.to_dict() for p in panels]


@router.get("/crm/sellable-potential/by-family", response_model=List[dict])
def get_by_family(
    dc_code: str = "*",
    clusters: Optional[str] = Query(None),
    svc: SellableService = Depends(_sellable),
):
    summary = svc.compute_summary(
        dc_code=dc_code,
        selected_clusters=_parse_clusters(clusters),
    )
    return [f.to_dict() for f in summary.families]


# ---------------------------------------------------------------------------
# Metric tags
# ---------------------------------------------------------------------------


@router.get("/crm/metric-tags", response_model=List[MetricValueRow])
def get_metric_tags(
    prefix: Optional[str] = None,
    scope_type: str = "global",
    scope_id: str = "*",
    svc: SellableService = Depends(_sellable),
):
    found = svc.get_metric_dict(prefix=prefix, scope_type=scope_type, scope_id=scope_id)
    return [
        MetricValueRow(
            metric_key=mv.metric_key,
            value=mv.value,
            unit=mv.unit,
            scope_type=mv.scope_type,
            scope_id=mv.scope_id,
        )
        for mv in found.values()
    ]


@router.get("/crm/metric-tags/snapshots", response_model=List[MetricSnapshotRow])
def get_metric_snapshots(
    metric_key: str = Query(..., min_length=1),
    scope_id: str = "*",
    hours: int = 720,
    svc: SellableService = Depends(_sellable),
):
    rows = svc.list_metric_snapshots(metric_key=metric_key, scope_id=scope_id, hours=hours)
    out: list[MetricSnapshotRow] = []
    for r in rows:
        ts = r.get("captured_at")
        out.append(MetricSnapshotRow(
            metric_key=r["metric_key"],
            scope_type=r["scope_type"],
            scope_id=r["scope_id"],
            value=float(r["value"]),
            unit=r["unit"],
            captured_at=ts.isoformat() if hasattr(ts, "isoformat") else (str(ts) if ts else None),
        ))
    return out


# ---------------------------------------------------------------------------
# Panel registry
# ---------------------------------------------------------------------------


@router.get("/crm/panels", response_model=List[PanelDefinitionRow])
def list_panels(webui: WebuiPool = Depends(_webui)):
    return webui.run_rows(sq.LIST_PANEL_DEFS)


@router.put("/crm/panels/{panel_key}", response_model=dict)
def upsert_panel(panel_key: str, body: PanelDefinitionUpsert, webui: WebuiPool = Depends(_webui)):
    if body.resource_kind not in {"cpu", "ram", "storage", "other"}:
        raise HTTPException(status_code=400, detail="resource_kind must be cpu|ram|storage|other")
    webui.execute(
        sq.UPSERT_PANEL_DEF,
        (
            panel_key,
            body.label,
            body.family,
            body.resource_kind,
            body.display_unit,
            int(body.sort_order),
            bool(body.enabled),
            body.notes,
            "settings-ui",
        ),
    )
    return {"status": "ok", "panel_key": panel_key}


@router.get("/crm/panels/{panel_key}/infra-source", response_model=PanelInfraSourceRow)
def get_infra_source(panel_key: str, dc_code: str = "*", webui: WebuiPool = Depends(_webui)):
    row = webui.run_one(sq.GET_INFRA_SOURCE, (panel_key, dc_code))
    if not row:
        return PanelInfraSourceRow(panel_key=panel_key, dc_code=dc_code)
    return row


@router.put("/crm/panels/{panel_key}/infra-source", response_model=dict)
def upsert_infra_source(
    panel_key: str,
    body: PanelInfraSourceUpsert,
    webui: WebuiPool = Depends(_webui),
):
    webui.execute(
        sq.UPSERT_INFRA_SOURCE,
        (
            panel_key,
            body.dc_code or "*",
            body.source_table,
            body.total_column,
            body.total_unit,
            body.allocated_table,
            body.allocated_column,
            body.allocated_unit,
            body.filter_clause,
            body.notes,
            "settings-ui",
        ),
    )
    return {"status": "ok", "panel_key": panel_key, "dc_code": body.dc_code or "*"}


# ---------------------------------------------------------------------------
# Resource ratios
# ---------------------------------------------------------------------------


@router.get("/crm/resource-ratios", response_model=List[ResourceRatioRow])
def list_ratios(webui: WebuiPool = Depends(_webui)):
    return webui.run_rows(sq.LIST_RATIOS)


@router.put("/crm/resource-ratios/{family}", response_model=dict)
def upsert_ratio(family: str, body: ResourceRatioUpsert, webui: WebuiPool = Depends(_webui)):
    if body.cpu_per_unit <= 0 or body.ram_gb_per_unit <= 0 or body.storage_gb_per_unit <= 0:
        raise HTTPException(status_code=400, detail="ratios must be > 0")
    webui.execute(
        sq.UPSERT_RATIO,
        (
            family,
            body.dc_code or "*",
            float(body.cpu_per_unit),
            float(body.ram_gb_per_unit),
            float(body.storage_gb_per_unit),
            body.notes,
            "settings-ui",
        ),
    )
    return {"status": "ok", "family": family, "dc_code": body.dc_code or "*"}


# ---------------------------------------------------------------------------
# Unit conversions
# ---------------------------------------------------------------------------


@router.get("/crm/unit-conversions", response_model=List[UnitConversionRow])
def list_unit_conversions(webui: WebuiPool = Depends(_webui)):
    return webui.run_rows(sq.LIST_UNIT_CONVERSIONS)


@router.put("/crm/unit-conversions/{from_unit}/{to_unit}", response_model=dict)
def upsert_unit_conversion(
    from_unit: str,
    to_unit: str,
    body: UnitConversionUpsert,
    webui: WebuiPool = Depends(_webui),
):
    if body.factor <= 0:
        raise HTTPException(status_code=400, detail="factor must be > 0")
    if body.operation not in {"multiply", "divide"}:
        raise HTTPException(status_code=400, detail="operation must be multiply|divide")
    webui.execute(
        sq.UPSERT_UNIT_CONVERSION,
        (
            from_unit,
            to_unit,
            float(body.factor),
            body.operation,
            bool(body.ceil_result),
            body.notes,
            "settings-ui",
        ),
    )
    return {"status": "ok", "from_unit": from_unit, "to_unit": to_unit}


@router.delete("/crm/unit-conversions/{from_unit}/{to_unit}", response_model=dict)
def delete_unit_conversion(
    from_unit: str,
    to_unit: str,
    webui: WebuiPool = Depends(_webui),
):
    n = webui.execute(sq.DELETE_UNIT_CONVERSION, (from_unit, to_unit))
    return {"status": "ok", "rows_deleted": int(n)}
