"""Pydantic response models for HMDL collector read API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


LokiSyncStatus = Literal["loki_synced", "not_synced"]
InclusionCategory = Literal[
    "monitored",
    "not_monitored",
    "customer_environment",
    "connectivity_issue",
    "missing_from_loki",
    "pending_distribution",
]


class ProxyNode(BaseModel):
    proxy_id: str
    proxy_nifi_host: str
    loki_sync_status: LokiSyncStatus
    target_count: int = 0
    distributed_count: int = 0
    last_sync_at: datetime | None = None
    last_sync_status: str | None = None
    last_run_id: str | None = None


class TopologyNode(BaseModel):
    dc_code: str
    role: Literal["hub", "spoke"]
    loki_sync_status: LokiSyncStatus
    proxies: list[ProxyNode] = Field(default_factory=list)


class TopologyEdge(BaseModel):
    from_dc: str
    to_dc: str


class TopologyResponse(BaseModel):
    hub_dc: str
    generated_at: datetime
    last_prod_run_id: str | None = None
    last_prod_run_at: datetime | None = None
    nodes: list[TopologyNode]
    edges: list[TopologyEdge]
    synced_dc_count: int
    total_dc_count: int


class SyncSummaryResponse(BaseModel):
    generated_at: datetime
    last_prod_run_id: str | None = None
    last_prod_run_at: datetime | None = None
    synced_dc_count: int
    total_dc_count: int
    synced_proxy_count: int
    total_proxy_count: int
    dc_statuses: dict[str, LokiSyncStatus]


class SyncLogEntry(BaseModel):
    id: int
    run_id: str
    awx_job_id: str | None = None
    proxy_id: str
    collector_id: int | None = None
    added_count: int = 0
    removed_count: int = 0
    unchanged_count: int = 0
    status: str
    dry_run: bool = False
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ProxyDetailResponse(BaseModel):
    proxy_id: str
    dc_code: str | None = None
    proxy_nifi_host: str | None = None
    loki_sync_status: LokiSyncStatus
    target_count: int = 0
    distributed_count: int = 0
    last_sync: SyncLogEntry | None = None
    recent_syncs: list[SyncLogEntry] = Field(default_factory=list)


class DiffEntry(BaseModel):
    run_id: str
    proxy_id: str
    conf_key: str | None = None
    action: str
    ip: str
    reason: str | None = None
    created_at: datetime | None = None


class DcSummaryResponse(BaseModel):
    dc_code: str
    loki_sync_status: LokiSyncStatus
    proxy_count: int
    target_count: int
    last_prod_run_id: str | None = None
    last_prod_run_at: datetime | None = None
    recent_diffs: list[DiffEntry] = Field(default_factory=list)
    category_counts: dict[str, int] = Field(default_factory=dict)


class TargetRow(BaseModel):
    entity_name: str | None = None
    ip: str
    proxy_id: str
    conf_key: str | None = None
    inclusion_category: InclusionCategory
    platform_status: str | None = None
    last_distributed_at: datetime | None = None
    last_check_status: str | None = None
    tenant_name: str | None = None
    manufacturer: str | None = None
    extra: dict[str, Any] | None = None


class TargetsResponse(BaseModel):
    dc_code: str
    total: int
    items: list[TargetRow]
    category_filter: str | None = None


class RunsResponse(BaseModel):
    items: list[SyncLogEntry]
