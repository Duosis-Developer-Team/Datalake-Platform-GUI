"""
CRM configuration endpoints — operator-managed thresholds, price overrides,
calc variables and discovery counts. All persisted in webui-db.

Routes:
  GET  /crm/config/thresholds
  PUT  /crm/config/thresholds
  DELETE /crm/config/thresholds/{threshold_id}
  GET  /crm/config/price-overrides
  PUT  /crm/config/price-overrides/{productid}
  DELETE /crm/config/price-overrides/{productid}
  GET  /crm/config/variables
  PUT  /crm/config/variables/{config_key}
  GET  /crm/config/discovery-counts
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request

from app.db.queries import crm_sales as sq
from app.models.schemas import (
    CalcConfigRow,
    CalcConfigUpsert,
    CrmDiscoveryCount,
    PriceOverrideRow,
    PriceOverrideUpsert,
    ThresholdConfigRow,
    ThresholdUpsert,
)
from app.services.crm_config_service import CrmConfigService
from app.services.sales_service import SalesService
from app.services.webui_db import WebuiPool

router = APIRouter()


def _config(request: Request) -> CrmConfigService:
    webui: WebuiPool = request.app.state.webui
    if webui is None or not webui.is_available:
        raise HTTPException(status_code=503, detail="WebUI configuration DB not available")
    return CrmConfigService(webui)


def _sales(request: Request) -> SalesService:
    return request.app.state.sales


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------


@router.get("/crm/config/thresholds", response_model=List[ThresholdConfigRow])
def list_thresholds(cfg: CrmConfigService = Depends(_config)):
    return cfg.list_thresholds()


@router.put("/crm/config/thresholds", response_model=dict)
def upsert_threshold(body: ThresholdUpsert, cfg: CrmConfigService = Depends(_config)):
    if body.sellable_limit_pct < 0 or body.sellable_limit_pct > 100:
        raise HTTPException(status_code=400, detail="sellable_limit_pct must be between 0 and 100")
    cfg.upsert_threshold(
        resource_type=body.resource_type,
        dc_code=body.dc_code or "*",
        sellable_limit_pct=body.sellable_limit_pct,
        notes=body.notes,
        updated_by="settings-ui",
        panel_key=body.panel_key,
    )
    return {
        "status": "ok",
        "resource_type": body.resource_type,
        "dc_code": body.dc_code or "*",
        "panel_key": body.panel_key,
    }


@router.delete("/crm/config/thresholds/{threshold_id}", response_model=dict)
def delete_threshold(threshold_id: int, cfg: CrmConfigService = Depends(_config)):
    n = cfg.delete_threshold(threshold_id)
    return {"status": "ok", "id": threshold_id, "rows_deleted": n}


# ---------------------------------------------------------------------------
# Price overrides
# ---------------------------------------------------------------------------


@router.get("/crm/config/price-overrides", response_model=List[PriceOverrideRow])
def list_price_overrides(cfg: CrmConfigService = Depends(_config)):
    return cfg.list_price_overrides()


@router.put("/crm/config/price-overrides/{productid}", response_model=dict)
def upsert_price_override(
    productid: str,
    body: PriceOverrideUpsert,
    cfg: CrmConfigService = Depends(_config),
):
    if body.unit_price_tl < 0:
        raise HTTPException(status_code=400, detail="unit_price_tl must be >= 0")
    cfg.upsert_price_override(
        productid=productid,
        product_name=body.product_name,
        unit_price_tl=body.unit_price_tl,
        resource_unit=body.resource_unit,
        currency=body.currency,
        notes=body.notes,
        updated_by="settings-ui",
    )
    return {"status": "ok", "productid": productid}


@router.delete("/crm/config/price-overrides/{productid}", response_model=dict)
def delete_price_override(productid: str, cfg: CrmConfigService = Depends(_config)):
    n = cfg.delete_price_override(productid)
    return {"status": "ok", "productid": productid, "rows_deleted": n}


# ---------------------------------------------------------------------------
# Calc variables
# ---------------------------------------------------------------------------


@router.get("/crm/config/variables", response_model=List[CalcConfigRow])
def list_variables(cfg: CrmConfigService = Depends(_config)):
    return cfg.list_calc_config()


@router.put("/crm/config/variables/{config_key}", response_model=dict)
def upsert_variable(
    config_key: str,
    body: CalcConfigUpsert,
    cfg: CrmConfigService = Depends(_config),
):
    cfg.upsert_calc_config(
        config_key=config_key,
        config_value=body.config_value,
        value_type=body.value_type,
        description=body.description,
        updated_by="settings-ui",
    )
    return {"status": "ok", "config_key": config_key}


# ---------------------------------------------------------------------------
# CRM Overview — discovery table sizes (raw datalake counts)
# ---------------------------------------------------------------------------


@router.get("/crm/config/discovery-counts", response_model=List[CrmDiscoveryCount])
def list_discovery_counts(svc: SalesService = Depends(_sales)):
    """Row counts and last collection timestamp of discovery_crm_* tables."""
    rows = svc._run_query(sq.DISCOVERY_TABLE_COUNTS, ())
    out: List[dict] = []
    for r in rows:
        ts = r.get("last_collected")
        out.append({
            "table_name": r.get("table_name"),
            "row_count": int(r.get("row_count") or 0),
            "last_collected": ts.isoformat() if hasattr(ts, "isoformat") else (str(ts) if ts else None),
        })
    return out
