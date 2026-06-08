"""NetBox/Loki visualization exclusion endpoints (webui-db)."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request

from app.models.schemas import NetboxVizExclusionRow, NetboxVizExclusionUpsert
from app.services.netbox_config_service import NetboxConfigService
from app.services.webui_db import WebuiPool

router = APIRouter()


def _config(request: Request) -> NetboxConfigService:
    webui: WebuiPool = request.app.state.webui
    if webui is None or not webui.is_available:
        raise HTTPException(status_code=503, detail="WebUI configuration DB not available")
    return NetboxConfigService(webui)


@router.get("/netbox/config/visualization-exclusions", response_model=List[NetboxVizExclusionRow])
def list_visualization_exclusions(cfg: NetboxConfigService = Depends(_config)):
    return cfg.list_exclusions()


@router.put("/netbox/config/visualization-exclusions", response_model=dict)
def upsert_visualization_exclusion(
    body: NetboxVizExclusionUpsert,
    cfg: NetboxConfigService = Depends(_config),
):
    try:
        row = cfg.upsert_exclusion(
            view_scope=body.view_scope,
            dimension=body.dimension or "device_role",
            dimension_value=body.dimension_value,
            notes=body.notes,
            updated_by="settings-ui",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", **row}


@router.delete("/netbox/config/visualization-exclusions/{exclusion_id}", response_model=dict)
def delete_visualization_exclusion(exclusion_id: int, cfg: NetboxConfigService = Depends(_config)):
    n = cfg.delete_exclusion(exclusion_id)
    return {"status": "ok", "id": exclusion_id, "rows_deleted": n}
