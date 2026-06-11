"""Dataclasses returned by the SellableService and consumed by the routers.

Kept in `shared/` (no DB or framework imports) so customer-api, datacenter-api,
and unit tests can all share a single contract.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class PanelDefinition:
    panel_key: str
    label: str
    family: str
    resource_kind: str        # cpu | ram | storage | other
    display_unit: str
    sort_order: int = 100
    enabled: bool = True
    notes: str | None = None


@dataclass(frozen=True)
class InfraSource:
    panel_key: str
    dc_code: str = "*"
    source_table: str | None = None
    total_column: str | None = None
    total_unit: str | None = None
    allocated_table: str | None = None
    allocated_column: str | None = None
    allocated_unit: str | None = None
    filter_clause: str | None = None
    manual_total: float | None = None
    manual_allocated: float | None = None
    notes: str | None = None


@dataclass(frozen=True)
class ResourceRatio:
    family: str
    dc_code: str = "*"
    cpu_per_unit: float = 1.0
    ram_gb_per_unit: float = 8.0
    storage_gb_per_unit: float = 100.0
    notes: str | None = None


@dataclass(frozen=True)
class UnitConversion:
    from_unit: str
    to_unit: str
    factor: float
    operation: str = "divide"      # multiply | divide
    ceil_result: bool = False
    notes: str | None = None


@dataclass
class PanelResult:
    """Computed sellable view of a single panel."""

    panel_key: str
    label: str
    family: str
    resource_kind: str
    display_unit: str
    dc_code: str = "*"
    total: float = 0.0
    allocated: float = 0.0
    threshold_pct: float = 80.0
    sellable_raw: float = 0.0
    sellable_constrained: float = 0.0
    unit_price_tl: float = 0.0
    potential_tl: float = 0.0
    ratio_bound: bool = False              # True if constrained < raw
    has_infra_source: bool = False
    has_price: bool = False
    notes: list[str] = field(default_factory=list)
    # Architecture-aware storage range (IBM capacity shared by KM + Power).
    # None means "no range — single value" (sellable_constrained applies).
    sellable_min: float | None = None
    sellable_max: float | None = None
    potential_tl_min: float | None = None
    potential_tl_max: float | None = None
    # Dual CPU sellable tracks (physical GHz vs effective sales units).
    sellable_physical: float | None = None
    sellable_effective: float | None = None
    potential_tl_physical: float | None = None
    potential_tl_effective: float | None = None
    # host_based | cluster_fallback — how virt CPU/RAM sellable was computed.
    computation_mode: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FamilyAggregate:
    family: str
    label: str
    dc_code: str = "*"
    panels: list[PanelResult] = field(default_factory=list)
    total_potential_tl: float = 0.0
    total_sellable_constrained_units: dict[str, float] = field(default_factory=dict)  # by resource_kind
    constrained_loss_tl: float = 0.0       # raw potential - constrained potential
    computation_mode: str | None = None
    total_potential_tl_min: float | None = None
    total_potential_tl_max: float | None = None
    mapped_panel_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "label": self.label,
            "dc_code": self.dc_code,
            "panels": [p.to_dict() for p in self.panels],
            "total_potential_tl": self.total_potential_tl,
            "total_sellable_constrained_units": self.total_sellable_constrained_units,
            "constrained_loss_tl": self.constrained_loss_tl,
            "computation_mode": self.computation_mode,
            "total_potential_tl_min": self.total_potential_tl_min,
            "total_potential_tl_max": self.total_potential_tl_max,
            "mapped_panel_count": self.mapped_panel_count,
        }


@dataclass
class DashboardSummary:
    dc_code: str
    total_potential_tl: float
    constrained_loss_tl: float
    ytd_sales_tl: float
    unmapped_product_count: int
    families: list[FamilyAggregate] = field(default_factory=list)
    total_potential_tl_min: float | None = None
    total_potential_tl_max: float | None = None
    mapped_panel_count: int = 0
    computation_modes: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dc_code": self.dc_code,
            "total_potential_tl": self.total_potential_tl,
            "constrained_loss_tl": self.constrained_loss_tl,
            "ytd_sales_tl": self.ytd_sales_tl,
            "unmapped_product_count": self.unmapped_product_count,
            "families": [f.to_dict() for f in self.families],
            "total_potential_tl_min": self.total_potential_tl_min,
            "total_potential_tl_max": self.total_potential_tl_max,
            "mapped_panel_count": self.mapped_panel_count,
            "computation_modes": self.computation_modes,
        }


@dataclass(frozen=True)
class MetricValue:
    metric_key: str
    value: float
    unit: str
    scope_type: str = "global"     # global | dc | customer
    scope_id: str = "*"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
