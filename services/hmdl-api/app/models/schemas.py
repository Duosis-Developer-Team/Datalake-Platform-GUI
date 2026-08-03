"""Pydantic response models for HMDL collector read API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


LokiSyncStatus = Literal["loki_synced", "not_synced"]
ProxyConfigStatus = Literal["configured", "no_configured_proxy"]
NodeRole = Literal["hub", "spoke", "source"]
EdgeType = Literal["collection", "distribution", "hub_spoke", "ingestion"]
EnvironmentStatus = Literal["connected", "connectivity_issue", "no_configured_proxy"]
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
    location_id: int | None = None
    location_name: str
    dc_code: str | None = None
    description: str | None = None
    site_name: str | None = None
    role: NodeRole
    proxy_config_status: ProxyConfigStatus
    loki_sync_status: LokiSyncStatus | None = None
    environment_status: EnvironmentStatus | None = None
    connectivity_issue_count: int = 0
    proxies: list[ProxyNode] = Field(default_factory=list)


class SourceNode(BaseModel):
    id: str
    label: str
    role: Literal["source"] = "source"


class TopologyEdge(BaseModel):
    from_dc: str
    to_dc: str
    edge_type: EdgeType = "hub_spoke"


class TopologyResponse(BaseModel):
    hub_dc: str
    source_node: SourceNode | None = None
    generated_at: datetime
    last_prod_run_id: str | None = None
    last_prod_run_at: datetime | None = None
    nodes: list[TopologyNode]
    edges: list[TopologyEdge]
    synced_dc_count: int
    total_dc_count: int
    configured_location_count: int = 0
    no_configured_proxy_count: int = 0
    connected_environment_count: int = 0
    connectivity_issue_environment_count: int = 0
    dc_statuses: dict[str, LokiSyncStatus] = Field(default_factory=dict)


class SyncSummaryResponse(BaseModel):
    generated_at: datetime
    last_prod_run_id: str | None = None
    last_prod_run_at: datetime | None = None
    synced_dc_count: int
    total_dc_count: int
    configured_location_count: int = 0
    no_configured_proxy_count: int = 0
    connected_environment_count: int = 0
    connectivity_issue_environment_count: int = 0
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
    location_name: str | None = None
    proxy_config_status: ProxyConfigStatus = "configured"
    environment_status: EnvironmentStatus | None = None
    connectivity_issue_count: int = 0
    loki_sync_status: LokiSyncStatus
    proxy_count: int
    target_count: int
    last_prod_run_id: str | None = None
    last_prod_run_at: datetime | None = None
    recent_diffs: list[DiffEntry] = Field(default_factory=list)
    category_counts: dict[str, int] = Field(default_factory=dict)


class LocationRow(BaseModel):
    location_id: int | None = None
    location_name: str
    dc_code: str | None = None
    site_name: str | None = None
    description: str | None = None
    proxy_config_status: ProxyConfigStatus
    loki_sync_status: LokiSyncStatus | None = None
    environment_status: EnvironmentStatus | None = None
    connectivity_issue_count: int = 0
    proxy_count: int = 0


class LocationsResponse(BaseModel):
    items: list[LocationRow]
    total: int


class TargetRow(BaseModel):
    entity_name: str | None = None
    ip: str
    proxy_id: str
    conf_key: str | None = None
    inclusion_category: InclusionCategory
    platform_status: str | None = None
    last_distributed_at: datetime | None = None
    last_check_status: str | None = None
    last_check_at: datetime | None = None
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


# --- Automation health (schedule / freshness of HMDL automations) ---

AutomationStatus = Literal["fresh", "stale", "dead", "unknown"]


class AutomationRow(BaseModel):
    key: str
    label: str
    cadence: str
    last_run_at: datetime | None = None
    age_hours: float | None = None
    status: AutomationStatus
    warn_hours: float
    dead_hours: float
    extra: dict[str, Any] = Field(default_factory=dict)


class AutomationCounts(BaseModel):
    fresh: int = 0
    stale: int = 0
    dead: int = 0
    unknown: int = 0
    alert: int = 0


class ProxyHealthRow(BaseModel):
    proxy_id: str
    dc_code: str | None = None
    proxy_nifi_host: str | None = None
    last_seen_at: datetime | None = None
    age_hours: float | None = None
    status: AutomationStatus


class ProxySummary(BaseModel):
    total: int = 0
    fresh: int = 0
    stale: int = 0
    dead: int = 0


class DataGaps(BaseModel):
    cluster_missing: int = 0
    ibm_missing: int = 0
    by_source: dict[str, int] = Field(default_factory=dict)


class DataFamily(BaseModel):
    family: str
    counts: AutomationCounts = Field(default_factory=AutomationCounts)
    sources: list[AutomationRow] = Field(default_factory=list)


class DataFlow(BaseModel):
    """One collection flow: a collector and every table it writes.

    ``age_hours`` is the age of the flow's oldest alerting member, or None when the
    flow is healthy. ``sources`` carries the member tables for UI drill-down.
    """
    key: str
    label: str
    status: str = "unknown"
    age_hours: float | None = None
    counts: AutomationCounts = Field(default_factory=AutomationCounts)
    sources: list[AutomationRow] = Field(default_factory=list)


class AutomationHealthResponse(BaseModel):
    generated_at: datetime | None = None
    automations: list[AutomationRow] = Field(default_factory=list)
    counts: AutomationCounts = Field(default_factory=AutomationCounts)
    proxies: list[ProxyHealthRow] = Field(default_factory=list)
    proxy_summary: ProxySummary = Field(default_factory=ProxySummary)
    data_gaps: DataGaps = Field(default_factory=DataGaps)
    # Data-collection freshness (newest-row age per collected DATA table), grouped
    # by platform family — served from the background snapshot. Complements the
    # AWX job-log automations above ("job ran" vs "data actually landed").
    data_families: list[DataFamily] = Field(default_factory=list)
    # Per-collection-flow rollup of the same freshness data. One dead collector is
    # one row here however many tables it feeds; data_counts is tallied over these.
    data_flows: list[DataFlow] = Field(default_factory=list)
    # Tables no service queries: reported so nothing is hidden, never counted.
    data_unmonitored: list[AutomationRow] = Field(default_factory=list)
    # MONITORED names that discovery did not return — a renamed or dropped table.
    # Surfaced so a stale curation entry is visible instead of silently ignored.
    data_missing: list[str] = Field(default_factory=list)
    data_counts: AutomationCounts = Field(default_factory=AutomationCounts)
    data_status: str = "computing"
    data_snapshot_at: datetime | None = None


# --- Datalake coverage (cluster / IBM host present-absent) ---

CoverageStatus = Literal["live", "stale", "missing", "extra", "offline", "unknown"]


class CoverageTargetIssue(BaseModel):
    dc_code: str | None = None
    platform: str | None = None
    dns: str | None = None
    proxy: str | None = None
    check_status: str | None = None
    network_access: bool | None = None


class CoverageBucket(BaseModel):
    total: int = 0
    collected: int = 0
    missing: int = 0
    live: int = 0
    offline: int = 0


class ClusterCoverageRow(BaseModel):
    source: str
    cluster_name: str | None = None
    dc: str
    parent_name: str | None = None
    # Resolved parent: `parent_key` joins to `VcenterCoverageRow.parent_key`.
    parent_key: str | None = None
    parent_display: str | None = None
    parent_ip: str | None = None
    # Discovery parent that lost to NetBox cluster_description (ADR-0031 §12).
    parent_conflict_with: str | None = None
    # Why no parent_key: no_hint | ambiguous | unknown_dc | unresolved_parent | no_collector.
    unmatched_reason: str | None = None
    expected_source: str | None = None
    collected: bool
    expected: bool
    is_live: bool
    last_collected: datetime | None = None
    status: CoverageStatus
    reason: str
    target_issues: list[CoverageTargetIssue] = Field(default_factory=list)


class IbmHostCoverageRow(BaseModel):
    servername: str | None = None
    dc: str
    parent_name: str | None = None
    parent_ip: str | None = None
    expected_source: str | None = None
    collected: bool
    expected: bool
    is_live: bool
    is_offline: bool = False
    last_collected: datetime | None = None
    status: CoverageStatus
    reason: str
    target_issues: list[CoverageTargetIssue] = Field(default_factory=list)


VcenterCoverageStatus = Literal[
    "live", "partial", "missing", "extra", "stale", "offline", "unknown"
]
ProbeStatus = Literal["ok", "partial", "fail", "unknown"]
ProbeReasonCategory = Literal[
    "ok", "script_missing", "auth", "network", "timeout", "no_data", "runner", "other"
]


class VcenterCoverageRow(BaseModel):
    source: str
    parent_name: str | None = None
    parent_key: str | None = None
    # "rollup" = AWX coverage_vcenter row; "endpoint" = synthesized from collector_target.
    origin: Literal["rollup", "endpoint"] = "rollup"
    endpoint_ip: str | None = None
    endpoint_name: str | None = None
    collector_check_status: str | None = None
    collector_network_ok: bool | None = None
    dc: str
    expected_clusters: int = 0
    collected_clusters: int = 0
    live_clusters: int = 0
    status: VcenterCoverageStatus = "unknown"
    checked_at: datetime | None = None
    # Collector script smoke for this endpoint IP (hmdl_datalake_collector_probe_log).
    probe_ok: int | None = None
    probe_total: int | None = None
    probe_status: ProbeStatus | None = None
    probe_reasons: str | None = None
    probe_checked_at: datetime | None = None


class BackupEndpointCoverageRow(BaseModel):
    source: str
    endpoint_ip: str | None = None
    endpoint_name: str | None = None
    dc: str
    collected: bool
    expected: bool
    expected_source: str | None = None
    network_ok: bool | None = None
    is_live: bool
    last_collected: datetime | None = None
    status: CoverageStatus
    reason: str
    checked_at: datetime | None = None
    # IP → collector_target (backup endpoints are already keyed by source IP).
    collector_check_status: str | None = None
    probe_ok: int | None = None
    probe_total: int | None = None
    probe_status: ProbeStatus | None = None
    probe_reasons: str | None = None
    probe_checked_at: datetime | None = None


class IbmHmcCoverageRow(BaseModel):
    """HMC (or 'unassigned' bucket) rollup over IBM Power hosts."""

    hmc_name: str | None = None
    endpoint_ip: str | None = None
    dc: str
    expected_hosts: int = 0
    collected_hosts: int = 0
    live_hosts: int = 0
    offline_hosts: int = 0
    status: VcenterCoverageStatus = "unknown"
    collector_check_status: str | None = None
    probe_ok: int | None = None
    probe_total: int | None = None
    probe_status: ProbeStatus | None = None
    probe_reasons: str | None = None
    probe_checked_at: datetime | None = None


class VcenterCoverageBucket(BaseModel):
    total: int = 0
    live: int = 0
    partial: int = 0
    missing: int = 0
    stale: int = 0
    extra: int = 0
    offline: int = 0


class CoverageSummary(BaseModel):
    cluster: dict[str, CoverageBucket] = Field(default_factory=dict)
    ibm_host: CoverageBucket = Field(default_factory=CoverageBucket)
    vcenter: VcenterCoverageBucket = Field(default_factory=VcenterCoverageBucket)
    ibm_hmc: VcenterCoverageBucket = Field(default_factory=VcenterCoverageBucket)
    backup_endpoint: dict[str, CoverageBucket] = Field(default_factory=dict)


class CoverageResponse(BaseModel):
    summary: CoverageSummary
    clusters: list[ClusterCoverageRow]
    ibm_hosts: list[IbmHostCoverageRow]
    vcenters: list[VcenterCoverageRow] = Field(default_factory=list)
    ibm_hmcs: list[IbmHmcCoverageRow] = Field(default_factory=list)
    backup_endpoints: list[BackupEndpointCoverageRow] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    dc_filter: str | None = None
    source_filter: str | None = None


# --- Ingest freshness (TASK-M1 / coverage_endpoint) ---

IngestVerdict = Literal[
    "healthy",
    "no_network",
    "network_ok_no_data",
    "stale",
    "unmatched",
]


class IngestHealthSummary(BaseModel):
    healthy: int = 0
    no_network: int = 0
    network_ok_no_data: int = 0
    stale: int = 0
    unmatched: int = 0
    total: int = 0


class IngestHealthRow(BaseModel):
    endpoint_ip: str
    collector_type: str
    proxy_id: str = ""
    entity_name: str | None = None
    dc_code: str | None = None
    tenant_name: str | None = None
    network_access: bool = False
    check_status: str | None = None
    last_check_at: datetime | None = None
    match_mode: str | None = None
    match_key: str | None = None
    bridge_via: str | None = None
    bridge_resolved: str | None = None
    last_ingest_at: datetime | None = None
    ingest_age_hours: float | None = None
    ingest_stale: bool = False
    stale_after_hours: int = 6
    verdict: IngestVerdict
    detail_message: str = ""
    checked_at: datetime | None = None


class IngestHealthResponse(BaseModel):
    summary: IngestHealthSummary
    items: list[IngestHealthRow]
    dc_filter: str | None = None
    collector_type_filter: str | None = None
    verdict_filter: str | None = None


# --- Collector script smoke (collector_probe_log) ---


class ProbeHealthSummary(BaseModel):
    endpoints: int = 0
    probes: int = 0
    ok: int = 0
    fail: int = 0
    scripts: int = 0
    last_probe_at: datetime | None = None


class ProbeScriptRow(BaseModel):
    """One collector script (`probe_id`) across the fleet."""

    probe_id: str
    collector_type: str
    product: str
    bucket: str = ""
    endpoints: int = 0
    ok: int = 0
    fail: int = 0
    status: ProbeStatus = "unknown"
    last_probe_at: datetime | None = None


class ProbeMatrixCell(BaseModel):
    probe_id: str
    dc: str
    ok: int = 0
    fail: int = 0
    total: int = 0
    status: ProbeStatus = "unknown"
    last_probe_at: datetime | None = None


class ProbeReasonRow(BaseModel):
    category: ProbeReasonCategory
    reason: str
    count: int = 0
    probe_ids: list[str] = Field(default_factory=list)
    dcs: list[str] = Field(default_factory=list)


class ProbeEndpointRow(BaseModel):
    probe_id: str
    collector_type: str
    product: str
    bucket: str = ""
    dc: str
    proxy_id: str | None = None
    target_host: str
    entity_name: str | None = None
    success: bool
    reason: str = ""
    reason_category: ProbeReasonCategory = "other"
    exit_code: int | None = None
    duration_sec: float | None = None
    stdout_bytes: int | None = None
    stderr_bytes: int | None = None
    stdout_head: str | None = None
    stderr_head: str | None = None
    run_id: str = ""
    awx_job_id: str | None = None
    finished_at: datetime | None = None


class ProbeRunnerError(BaseModel):
    """Probe infrastructure fault (unparsable batch output), not a collector verdict."""

    run_id: str
    awx_job_id: str | None = None
    dc: str
    proxy_id: str | None = None
    reason: str = ""
    finished_at: datetime | None = None


class ProbeHealthResponse(BaseModel):
    summary: ProbeHealthSummary
    scripts: list[ProbeScriptRow] = Field(default_factory=list)
    matrix: list[ProbeMatrixCell] = Field(default_factory=list)
    reasons: list[ProbeReasonRow] = Field(default_factory=list)
    items: list[ProbeEndpointRow] = Field(default_factory=list)
    runner_errors: list[ProbeRunnerError] = Field(default_factory=list)
    dcs: list[str] = Field(default_factory=list)
    dc_filter: str | None = None
    probe_filter: str | None = None
