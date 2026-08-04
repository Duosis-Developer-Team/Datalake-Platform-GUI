"""Colocation sellable rack-role rule endpoints (webui-db)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.models.schemas import ColocationRoleRulesUpdate
from app.services.colocation_role_rule_service import (
    ColocationRoleRuleService,
    get_role_rule_service,
)

router = APIRouter()


def _service(request: Request) -> ColocationRoleRuleService:
    """Reuse the app-scoped instance so its 30s memo is shared, not per-request."""
    return get_role_rule_service(request.app)


@router.get("/colocation/role-rules", response_model=dict)
def get_role_rules(request: Request):
    svc = _service(request)
    rules = svc.load_rules()
    return {
        "rules": [
            {"role_id": rid, "sellable": flag}
            for rid, flag in sorted(rules.sellable.items())
        ],
        "catalog": svc.role_catalog(),
        "etag": rules.etag,
        # degraded=True means these numbers come from the built-in default,
        # not from the operator's saved config. The screen shows a banner and
        # disables saving rather than letting someone overwrite config they
        # cannot currently see.
        "degraded": not svc.is_available,
    }


@router.put("/colocation/role-rules", response_model=dict)
def put_role_rules(body: ColocationRoleRulesUpdate, request: Request):
    svc = _service(request)
    if not svc.is_available:
        raise HTTPException(status_code=503, detail="WebUI configuration DB not available")
    if not body.rules:
        raise HTTPException(status_code=400, detail="rules must not be empty")
    rules = svc.save_rules(
        [r.model_dump() for r in body.rules],
        notes=body.notes,
        updated_by="settings-ui",
    )
    return {"status": "ok", "etag": rules.etag}
