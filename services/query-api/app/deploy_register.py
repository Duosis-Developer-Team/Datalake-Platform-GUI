"""Best-effort deploy self-registration to admin-api. Never raises.

Copied verbatim into each service's app/ package. Backend build contexts are
isolated (each Dockerfile COPYs only its own service dir), so a single shared
import is not possible; the file is intentionally tiny and duplicated.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def _resolve_env() -> dict[str, str | None]:
    return {
        "version": os.environ.get("APP_VERSION") or os.environ.get("GIT_SHA") or "local",
        "git_sha": os.environ.get("GIT_SHA"),
        "image_tag": os.environ.get("IMAGE_TAG"),
        "environment": os.environ.get("DEPLOY_ENV", "production"),
    }


def _direct_db_insert(service: str, version: str, git_sha, image_tag, environment) -> None:
    """Write the deployment row straight to the auth DB (admin-api owns it)."""
    from app import database as _db

    _db.execute(
        "INSERT INTO service_deployments (service, version, git_sha, image_tag, environment) "
        "VALUES (%s, %s, %s, %s, %s)",
        (service, version, git_sha, image_tag, environment),
    )


def register_this_service(service: str) -> None:
    try:
        env = _resolve_env()
        admin_url = (os.environ.get("ADMIN_API_URL") or "").rstrip("/")
        if not admin_url:
            # Only admin-api owns the auth DB — it may write directly. Other services
            # without an ADMIN_API_URL simply skip (their `app.database` is a different DB).
            if service == "admin-api":
                try:
                    _direct_db_insert(
                        service, env["version"], env["git_sha"], env["image_tag"], env["environment"]
                    )
                except Exception:
                    logger.warning("deploy registration (direct DB) skipped for %s", service)
            else:
                logger.info("deploy registration skipped for %s: ADMIN_API_URL unset", service)
            return
        import httpx

        httpx.post(
            f"{admin_url}/api/v1/versions/deployments",
            json={
                "service": service,
                "version": env["version"],
                "git_sha": env["git_sha"],
                "image_tag": env["image_tag"],
                "environment": env["environment"],
            },
            timeout=5,
        )
    except Exception as exc:  # best-effort: never block startup
        logger.warning("deploy registration skipped for %s: %s", service, exc)
