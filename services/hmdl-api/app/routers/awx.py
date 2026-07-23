"""AWX control routes: runtime config (extra_vars), launch, job status, schedules."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import awx_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/awx", tags=["awx"])


class ConfigUpdate(BaseModel):
    extra_vars: dict


class LaunchRequest(BaseModel):
    extra_vars: dict | None = None


class ScheduleUpdate(BaseModel):
    enabled: bool


@router.get("/config")
def get_config():
    if not awx_client.is_configured():
        return {
            "awx_available": False,
            "reason": awx_client.not_configured_reason(),
            "extra_vars": {},
            "schedules": [],
        }
    try:
        extra_vars = awx_client.get_extra_vars()
        schedules = awx_client.list_schedules()
    except Exception as exc:  # noqa: BLE001
        logger.warning("AWX config fetch failed: %s", exc)
        return {"awx_available": False, "reason": str(exc), "extra_vars": {}, "schedules": []}
    return {"awx_available": True, "reason": None, "extra_vars": extra_vars, "schedules": schedules}


@router.put("/config")
def put_config(body: ConfigUpdate):
    if not awx_client.is_configured():
        raise HTTPException(status_code=503, detail=awx_client.not_configured_reason())
    try:
        updated = awx_client.patch_extra_vars(body.extra_vars)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"AWX update failed: {exc}") from exc
    return {"awx_available": True, "extra_vars": updated}


@router.post("/launch")
def launch(body: LaunchRequest):
    if not awx_client.is_configured():
        raise HTTPException(status_code=503, detail=awx_client.not_configured_reason())
    try:
        result = awx_client.launch(body.extra_vars)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"AWX launch failed: {exc}") from exc
    # ignored_fields tells the caller AWX dropped the launch-time extra_vars
    # (job template lacks "Prompt on launch" for Variables).
    return {"job_id": result.get("job_id"), "ignored_fields": result.get("ignored_fields") or {}}


@router.get("/jobs/{job_id}")
def get_job(job_id: int):
    if not awx_client.is_configured():
        raise HTTPException(status_code=503, detail=awx_client.not_configured_reason())
    try:
        return awx_client.get_job(job_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"AWX job fetch failed: {exc}") from exc


@router.get("/schedules")
def get_schedules():
    if not awx_client.is_configured():
        return {"awx_available": False, "items": [], "reason": awx_client.not_configured_reason()}
    try:
        return {"awx_available": True, "items": awx_client.list_schedules()}
    except Exception as exc:  # noqa: BLE001
        logger.warning("AWX schedules fetch failed: %s", exc)
        return {"awx_available": False, "items": [], "reason": str(exc)}


@router.put("/schedules/{schedule_id}")
def put_schedule(schedule_id: int, body: ScheduleUpdate):
    if not awx_client.is_configured():
        raise HTTPException(status_code=503, detail=awx_client.not_configured_reason())
    try:
        return awx_client.set_schedule_enabled(schedule_id, body.enabled)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"AWX schedule update failed: {exc}") from exc
