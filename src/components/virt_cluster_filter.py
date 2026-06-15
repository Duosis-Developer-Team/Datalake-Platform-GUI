"""Staged cluster filter bar for DC View virtualization tabs.

Draft selection in the popover checklist does not trigger compute callbacks until
Apply or debounce (800ms) commits to the applied Store. Empty draft ([]) means all
clusters are included (backend fast path).
"""
from __future__ import annotations

from dash import dcc, html
import dash_mantine_components as dmc
from dash_iconify import DashIconify

VIRT_CLUSTER_DEBOUNCE_MS = 800


def _ids(prefix: str) -> dict[str, str]:
    return {
        "draft": f"virt-{prefix}-cluster-draft",
        "applied": f"virt-{prefix}-cluster-applied",
        "all_clusters": f"virt-{prefix}-cluster-all",
        "debounce": f"virt-{prefix}-cluster-debounce",
        "apply": f"virt-{prefix}-cluster-apply",
        "select_all": f"virt-{prefix}-cluster-select-all",
        "summary_badge": f"virt-{prefix}-cluster-summary-badge",
        "trigger": f"virt-{prefix}-cluster-trigger",
        "popover": f"virt-{prefix}-cluster-popover",
        "search": f"virt-{prefix}-cluster-search",
        "checklist": f"virt-{prefix}-cluster-checklist",
    }


def _common_dc_prefix(clusters: list[str]) -> str:
    """Longest shared prefix ending at a hyphen boundary (e.g. DC13-)."""
    if not clusters:
        return ""
    if len(clusters) == 1:
        name = clusters[0]
        if "-" in name:
            return name.rsplit("-", 1)[0] + "-"
        return ""
    prefix = clusters[0]
    for name in clusters[1:]:
        while prefix and not name.startswith(prefix):
            if "-" in prefix:
                prefix = prefix.rsplit("-", 1)[0]
                if prefix:
                    prefix += "-"
            else:
                prefix = ""
                break
    if prefix and not prefix.endswith("-") and "-" in prefix:
        prefix = prefix.rsplit("-", 1)[0] + "-"
    return prefix if len(clusters) > 1 or prefix.endswith("-") else ""


def short_cluster_label(name: str, dc_prefix: str = "") -> str:
    """Display label with redundant DC prefix stripped."""
    if dc_prefix and name.startswith(dc_prefix):
        return name[len(dc_prefix) :]
    return name


def cluster_selection_summary(draft: list[str] | None, total: int) -> str:
    """Human-readable selection summary for badge and trigger."""
    if total <= 0:
        return "No clusters"
    selected = list(draft or [])
    if not selected or len(selected) >= total:
        return f"All {total} clusters"
    return f"{len(selected)} of {total} selected"


def checklist_value_from_draft(draft: list[str] | None, all_clusters: list[str]) -> list[str]:
    """Map draft store ([] = all) to CheckboxGroup checked values."""
    all_list = list(all_clusters or [])
    if not draft:
        return all_list
    return list(draft)


def draft_from_checklist(selected: list[str] | None, all_clusters: list[str]) -> list[str]:
    """Map CheckboxGroup values back to draft store ([] = all clusters)."""
    all_list = list(all_clusters or [])
    if not all_list:
        return []
    picked = list(selected or [])
    if len(picked) >= len(all_list) and set(picked) >= set(all_list):
        return []
    return picked


def _cluster_checkbox_items(clusters: list[str], dc_prefix: str) -> list:
    items: list = []
    for cluster in clusters:
        label = short_cluster_label(cluster, dc_prefix)
        items.append(
            html.Div(
                className="virt-cluster-checkbox-item",
                **{"data-label": label},
                children=dmc.Checkbox(label=label, value=cluster, size="sm"),
            )
        )
    return items


def build_virt_cluster_filter_bar(
    prefix: str,
    clusters: list[str],
    placeholder: str,
) -> list:
    """Return layout children: stores, debounce interval, compact filter toolbar."""
    ids = _ids(prefix)
    all_clusters = list(clusters or [])
    total = len(all_clusters)
    dc_prefix = _common_dc_prefix(all_clusters)
    summary = cluster_selection_summary([], total)
    checklist_initial = checklist_value_from_draft([], all_clusters)

    return [
        dcc.Store(id=ids["draft"], data=[]),
        dcc.Store(id=ids["applied"], data=[]),
        dcc.Store(id=ids["all_clusters"], data=all_clusters),
        dcc.Interval(
            id=ids["debounce"],
            interval=VIRT_CLUSTER_DEBOUNCE_MS,
            n_intervals=0,
            disabled=True,
        ),
        html.Div(
            className="nexus-card virt-cluster-filter",
            style={"padding": "12px 16px", "marginBottom": "16px"},
            children=[
                html.Div(
                    style={
                        "display": "flex",
                        "alignItems": "center",
                        "justifyContent": "space-between",
                        "gap": "12px",
                        "flexWrap": "wrap",
                    },
                    children=[
                        dmc.Group(
                            gap="sm",
                            children=[
                                DashIconify(
                                    icon="solar:filter-bold-duotone",
                                    width=22,
                                    color="#4318FF",
                                ),
                                dmc.Text("Clusters", fw=600, size="sm", c="#2B3674"),
                                dmc.Badge(
                                    id=ids["summary_badge"],
                                    children=summary,
                                    color="indigo",
                                    variant="light",
                                    size="lg",
                                    radius="md",
                                ),
                            ],
                        ),
                        dmc.Group(
                            gap="xs",
                            children=[
                                dmc.Popover(
                                    id=ids["popover"],
                                    opened=False,
                                    position="bottom-end",
                                    width=360,
                                    shadow="md",
                                    radius="md",
                                    withinPortal=True,
                                    closeOnClickOutside=True,
                                    trapFocus=True,
                                    children=[
                                        dmc.PopoverTarget(
                                            children=dmc.Button(
                                                id=ids["trigger"],
                                                children="Filter",
                                                variant="light",
                                                color="indigo",
                                                size="sm",
                                                radius="xl",
                                                leftSection=DashIconify(
                                                    icon="solar:alt-arrow-down-linear",
                                                    width=14,
                                                ),
                                            ),
                                        ),
                                        dmc.PopoverDropdown(
                                            className="virt-cluster-filter-panel",
                                            children=[
                                                dmc.TextInput(
                                                    id=ids["search"],
                                                    placeholder="Search clusters…",
                                                    size="sm",
                                                    mb="sm",
                                                    leftSection=DashIconify(
                                                        icon="solar:magnifer-linear",
                                                        width=16,
                                                        color="#A3AED0",
                                                    ),
                                                ),
                                                dmc.ScrollArea(
                                                    type="auto",
                                                    mah=280,
                                                    children=dmc.CheckboxGroup(
                                                        id=ids["checklist"],
                                                        value=checklist_initial,
                                                        children=_cluster_checkbox_items(
                                                            all_clusters,
                                                            dc_prefix,
                                                        ),
                                                    ),
                                                ),
                                                dmc.Text(
                                                    placeholder or "Select clusters",
                                                    size="xs",
                                                    c="dimmed",
                                                    mt="xs",
                                                ),
                                            ],
                                        ),
                                    ],
                                ),
                                dmc.Group(
                                    gap="xs",
                                    children=[
                                        dmc.Button(
                                            id=ids["select_all"],
                                            children="Select all",
                                            variant="light",
                                            color="indigo",
                                            size="sm",
                                            radius="xl",
                                        ),
                                        dmc.Button(
                                            id=ids["apply"],
                                            children="Apply",
                                            variant="filled",
                                            color="indigo",
                                            size="sm",
                                            radius="xl",
                                        ),
                                    ],
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        ),
    ]


def virt_cluster_filter_ids(prefix: str) -> dict[str, str]:
    return _ids(prefix)
