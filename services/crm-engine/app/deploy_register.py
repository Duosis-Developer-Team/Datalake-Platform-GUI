"""Best-effort deploy self-registration to admin-api. Never raises.

Copied into each service's app/ package. Backend build contexts are isolated
(each Dockerfile COPYs only its own service dir), so a single shared import is
not possible; the file is intentionally tiny and duplicated. Only admin-api owns
the auth DB and writes directly; every other service posts to ADMIN_API_URL.
"""

from __future__ import annotations

import logging
import os
import time

logger = logging.getLogger(__name__)

_RETRIES = 3
_BACKOFF_SECONDS = 2


def _resolve_env() -> dict[str, str | None]:
    return {
        "version": os.environ.get("APP_VERSION") or os.environ.get("GIT_SHA") or "local",
        "git_sha": os.environ.get("GIT_SHA"),
        "image_tag": os.environ.get("IMAGE_TAG"),
        "environment": os.environ.get("DEPLOY_ENV", "production"),
    }


def register_this_service(service: str) -> None:
    try:
        env = _resolve_env()
        admin_url = (os.environ.get("ADMIN_API_URL") or "").rstrip("/")
        if not admin_url:
            logger.info("deploy registration skipped for %s: ADMIN_API_URL unset", service)
            return
        import httpx

        payload = {
            "service": service,
            "version": env["version"],
            "git_sha": env["git_sha"],
            "image_tag": env["image_tag"],
            "environment": env["environment"],
        }
        # Retry a few times: admin-api may not be accepting requests yet when this
        # service starts (startup race). A single attempt otherwise silently drops
        # the registration — the gap this fixes (NB-3).
        for attempt in range(_RETRIES):
            try:
                httpx.post(f"{admin_url}/api/v1/versions/deployments", json=payload, timeout=5)
                return
            except Exception as exc:  # noqa: BLE001
                if attempt + 1 >= _RETRIES:
                    logger.warning(
                        "deploy registration for %s failed after %d attempts: %s",
                        service, _RETRIES, exc,
                    )
                else:
                    time.sleep(_BACKOFF_SECONDS * (attempt + 1))
    except Exception as exc:  # best-effort: never block startup
        logger.warning("deploy registration skipped for %s: %s", service, exc)
