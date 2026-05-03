"""Metric tagging service.

Owns the dot-notation namespace (e.g. ``virtualization.hyperconverged.ram.total``)
used by the Sellable Potential dashboard to expose computed numbers in a
uniform shape suitable for downstream dashboards, exports and trending.

Responsibilities:
    * Build canonical metric_keys from family + resource_kind + measure.
    * Cache the latest values in process memory (fast O(1) lookup).
    * Persist a snapshot row per (metric_key, scope_type, scope_id, captured_at)
      into ``gui_metric_snapshot`` for audit and trend analysis.

The runtime cache is intentionally process-local; for cross-pod sharing the
caller can chain a Redis writer (``app.services.cache_service``). Snapshots
are the canonical historical record.
"""
from __future__ import annotations

import logging
import threading
from typing import Iterable

from app.db.queries import sellable as sq
from app.services.webui_db import WebuiPool
from shared.sellable.models import MetricValue

logger = logging.getLogger(__name__)


_FAMILY_TO_NAMESPACE: dict[str, str] = {
    "virt_hyperconverged":      "virtualization.hyperconverged",
    "virt_classic":             "virtualization.classic",
    "virt_power":               "virtualization.power",
    "virt_intel_hana":          "virtualization.intel_hana",
    "virt_power_hana":          "virtualization.power_hana",
    "backup_veeam_replication": "backup.veeam_replication",
    "backup_zerto_replication": "backup.zerto_replication",
    "backup_netbackup":         "backup.netbackup",
    "backup_image":             "backup.image",
    "backup_offsite":           "backup.offsite",
    "backup_remote":            "backup.remote",
    "backup_veeam":             "backup.veeam",
    "storage_s3":               "storage.s3",
    "firewall":                 "security.firewall",
    "loadbalancer":             "network.loadbalancer",
    "license_microsoft":        "licensing.microsoft",
    "license_redhat":           "licensing.redhat",
    "license_other":            "licensing.other",
    "network":                  "network",
    "dc_hosting":               "datacenter.hosting",
    "dc_energy":                "datacenter.energy",
    "mgmt_database":            "mgmt.database",
    "mgmt_os":                  "mgmt.os",
    "mgmt_monitoring":          "mgmt.monitoring",
    "mgmt_backup":              "mgmt.backup",
    "mgmt_security":            "mgmt.security",
    "mgmt_replication":         "mgmt.replication",
    "mgmt_misc":                "mgmt.misc",
    "public_cloud":             "public_cloud",
    "other":                    "other",
}


def family_namespace(family: str) -> str:
    return _FAMILY_TO_NAMESPACE.get(family, family.replace("_", "."))


def build_metric_key(family: str, resource_kind: str, measure: str) -> str:
    """Compose a tag like ``virtualization.hyperconverged.ram.total``.

    ``measure`` is a free-form leaf (``total``, ``allocated``, ``sellable_raw``,
    ``sellable_constrained``, ``unit_price_tl``, ``potential_tl``).
    """
    ns = family_namespace(family)
    return f"{ns}.{resource_kind}.{measure}"


class TaggingService:
    """Runtime cache + DB snapshot writer for metric tags."""

    def __init__(self, webui: WebuiPool) -> None:
        self._webui = webui
        self._cache: dict[tuple[str, str, str], MetricValue] = {}
        self._lock = threading.Lock()

    # ---- cache --------------------------------------------------------

    def set(self, mv: MetricValue) -> None:
        key = (mv.metric_key, mv.scope_type, mv.scope_id)
        with self._lock:
            self._cache[key] = mv

    def get(self, metric_key: str, scope_type: str = "global", scope_id: str = "*") -> MetricValue | None:
        return self._cache.get((metric_key, scope_type, scope_id))

    def all_with_prefix(self, prefix: str | None = None,
                        scope_type: str = "global", scope_id: str = "*") -> dict[str, MetricValue]:
        """Snapshot of cache entries matching ``prefix`` (dot-aware)."""
        out: dict[str, MetricValue] = {}
        with self._lock:
            for (key, st, sid), mv in self._cache.items():
                if scope_type and st != scope_type:
                    continue
                if scope_id and sid != scope_id:
                    continue
                if prefix and not key.startswith(prefix):
                    continue
                out[key] = mv
        return out

    # ---- persistence --------------------------------------------------

    def snapshot(self, metrics: Iterable[MetricValue]) -> int:
        """Write metrics to ``gui_metric_snapshot``. Returns rows attempted."""
        if not self._webui or not self._webui.is_available:
            return 0
        count = 0
        for mv in metrics:
            try:
                self._webui.execute(
                    sq.INSERT_METRIC_SNAPSHOT,
                    (mv.metric_key, mv.scope_type, mv.scope_id, float(mv.value), mv.unit),
                )
                count += 1
            except Exception:  # noqa: BLE001 - one row should not abort the loop
                logger.exception("TaggingService: snapshot write failed for %s", mv.metric_key)
        return count

    # ---- helpers ------------------------------------------------------

    @staticmethod
    def measures_from_panel(panel) -> list[tuple[str, float, str]]:
        """Return [(measure, value, unit)] tuples extracted from a PanelResult."""
        return [
            ("total",                 float(panel.total),                panel.display_unit),
            ("allocated",             float(panel.allocated),            panel.display_unit),
            ("sellable_raw",          float(panel.sellable_raw),         panel.display_unit),
            ("sellable_constrained",  float(panel.sellable_constrained), panel.display_unit),
            ("unit_price_tl",         float(panel.unit_price_tl),        "TL"),
            ("potential_tl",          float(panel.potential_tl),         "TL"),
        ]
