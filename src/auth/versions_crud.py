"""Local (direct-DB) platform versioning reads/writes.

Mirrors the shapes returned by admin-api's versions router so
src/services/admin_client.py can fall back to this without ADMIN_API_URL.
"""

from __future__ import annotations

from typing import Any

from src.auth import db


def list_platform_releases() -> list[dict[str, Any]]:
    releases = db.fetch_all(
        """
        SELECT id, version, released_at::text AS released_at, title, notes, source
        FROM platform_releases
        ORDER BY released_at DESC, version DESC
        """
    )
    changes = db.fetch_all(
        "SELECT release_id, change_type, summary, commit_sha, scope FROM release_changes ORDER BY id"
    )
    deps = db.fetch_all(
        """
        SELECT service, version, git_sha, image_tag, environment, started_at::text AS started_at
        FROM service_deployments ORDER BY started_at DESC
        """
    )
    changes_by_release: dict[Any, list[dict]] = {}
    for c in changes:
        changes_by_release.setdefault(c["release_id"], []).append(c)
    deps_by_version: dict[str, list[dict]] = {}
    for d in deps:
        deps_by_version.setdefault(d["version"], []).append(d)
    out = []
    for r in releases:
        r = dict(r)
        r["changes"] = changes_by_release.get(r["id"], [])
        r["services"] = deps_by_version.get(r["version"], [])
        out.append(r)
    return out


def get_current_versions() -> list[dict[str, Any]]:
    return db.fetch_all(
        """
        SELECT DISTINCT ON (service)
               service, version, git_sha, image_tag, environment, started_at::text AS started_at
        FROM service_deployments
        ORDER BY service, started_at DESC
        """
    )


def register_deployment(
    service: str,
    version: str,
    git_sha: str | None = None,
    image_tag: str | None = None,
    environment: str = "production",
) -> None:
    db.execute(
        """
        INSERT INTO service_deployments (service, version, git_sha, image_tag, environment)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (service, version, git_sha, image_tag, environment),
    )
