"""Platform versioning: releases, current live versions, deploy self-registration."""

from __future__ import annotations

from fastapi import APIRouter

from app import database as db
from app.models import (
    RegisterDeploymentRequest,
    ReleaseChangeOut,
    ReleaseOut,
    ServiceDeploymentOut,
)

router = APIRouter()


def list_releases() -> list[ReleaseOut]:
    releases = db.fetch_all(
        """
        SELECT id, version, released_at::text AS released_at, title, notes, source
        FROM platform_releases
        ORDER BY released_at DESC, version DESC
        """
    )
    changes = db.fetch_all(
        """
        SELECT release_id, change_type, summary, commit_sha, scope
        FROM release_changes
        ORDER BY id
        """
    )
    deps = db.fetch_all(
        """
        SELECT service, version, git_sha, image_tag, environment,
               started_at::text AS started_at
        FROM service_deployments
        ORDER BY started_at DESC
        """
    )
    changes_by_release: dict[int, list[ReleaseChangeOut]] = {}
    for c in changes:
        changes_by_release.setdefault(c["release_id"], []).append(
            ReleaseChangeOut(**{k: c[k] for k in ("change_type", "summary", "commit_sha", "scope")})
        )
    deps_by_version: dict[str, list[ServiceDeploymentOut]] = {}
    for d in deps:
        deps_by_version.setdefault(d["version"], []).append(ServiceDeploymentOut(**d))
    out: list[ReleaseOut] = []
    for r in releases:
        out.append(
            ReleaseOut(
                version=r["version"],
                released_at=r["released_at"],
                title=r["title"],
                notes=r["notes"],
                source=r["source"],
                changes=changes_by_release.get(r["id"], []),
                services=deps_by_version.get(r["version"], []),
            )
        )
    return out


def current_versions() -> list[ServiceDeploymentOut]:
    rows = db.fetch_all(
        """
        SELECT DISTINCT ON (service)
               service, version, git_sha, image_tag, environment,
               started_at::text AS started_at
        FROM service_deployments
        ORDER BY service, started_at DESC
        """
    )
    return [ServiceDeploymentOut(**r) for r in rows]


def register_deployment(req: RegisterDeploymentRequest) -> ServiceDeploymentOut:
    db.execute(
        """
        INSERT INTO service_deployments (service, version, git_sha, image_tag, environment)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (req.service, req.version, req.git_sha, req.image_tag, req.environment),
    )
    return ServiceDeploymentOut(
        service=req.service,
        version=req.version,
        git_sha=req.git_sha,
        image_tag=req.image_tag,
        environment=req.environment,
    )


@router.get("/versions", response_model=list[ReleaseOut])
def get_versions():
    return list_releases()


@router.get("/versions/current", response_model=list[ServiceDeploymentOut])
def get_current():
    return current_versions()


@router.post("/versions/deployments", response_model=ServiceDeploymentOut)
def post_deployment(req: RegisterDeploymentRequest):
    return register_deployment(req)
