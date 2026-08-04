"""Colocation sellable rack-role rule endpoints (webui-db)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from app.models.schemas import ColocationRoleRulesUpdate
from app.services.colocation_role_rule_service import (
    ColocationRoleRuleService,
    get_role_rule_service,
)

logger = logging.getLogger(__name__)

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
    # Correctness comes from the etag in the cache key; this flush is only for
    # immediacy, so the colocation card moves now instead of after its 6h TTL.
    #
    # Only customer-api's OWN cache is flushed here. The sellable panel's cache
    # lives in the crm-engine process on a different Redis DB and is
    # unreachable from this endpoint -- it corrects itself within 30s when
    # crm-engine's memo expires and its etag changes. Do not add an HTTP call
    # to crm-engine for this.
    try:
        from app.services import cache_service as cache

        cache.delete_prefix("colocation:")
    except Exception:  # noqa: BLE001
        logger.warning("cache invalidation after role-rule save failed", exc_info=True)
    return {"status": "ok", "etag": rules.etag}
