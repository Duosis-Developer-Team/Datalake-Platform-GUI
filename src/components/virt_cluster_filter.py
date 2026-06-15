"""Staged cluster filter bar for DC View virtualization tabs.

Draft selection in MultiSelect does not trigger compute callbacks until Apply
or debounce (800ms) commits to the applied Store.
"""
from __future__ import annotations

from dash import dcc, html
import dash_mantine_components as dmc

VIRT_CLUSTER_DEBOUNCE_MS = 800


def _ids(prefix: str) -> dict[str, str]:
    return {
        "selector": f"virt-{prefix}-cluster-selector",
        "applied": f"virt-{prefix}-cluster-applied",
        "all_clusters": f"virt-{prefix}-cluster-all",
        "debounce": f"virt-{prefix}-cluster-debounce",
        "apply": f"virt-{prefix}-cluster-apply",
        "select_all": f"virt-{prefix}-cluster-select-all",
        "clear": f"virt-{prefix}-cluster-clear",
    }


def build_virt_cluster_filter_bar(
    prefix: str,
    clusters: list[str],
    placeholder: str,
) -> list:
    """Return layout children: stores, debounce interval, filter row."""
    ids = _ids(prefix)
    initial = list(clusters or [])
    return [
        dcc.Store(id=ids["applied"], data=initial),
        dcc.Store(id=ids["all_clusters"], data=initial),
        dcc.Interval(
            id=ids["debounce"],
            interval=VIRT_CLUSTER_DEBOUNCE_MS,
            n_intervals=0,
            disabled=True,
        ),
        html.Div(
            style={
                "display": "flex",
                "justifyContent": "flex-end",
                "alignItems": "center",
                "gap": "8px",
                "marginBottom": "16px",
                "flexWrap": "wrap",
            },
            children=[
                dmc.MultiSelect(
                    id=ids["selector"],
                    data=[{"label": c, "value": c} for c in initial],
                    value=initial,
                    clearable=True,
                    searchable=True,
                    nothingFoundMessage="No clusters",
                    placeholder=placeholder,
                    size="md",
                    radius="xl",
                    style={
                        "minWidth": "260px",
                        "flex": "1 1 260px",
                        "maxWidth": "640px",
                        "background": "#F8F9FC",
                    },
                ),
                dmc.Button(
                    id=ids["select_all"],
                    children="Select all",
                    variant="light",
                    color="indigo",
                    size="sm",
                    radius="xl",
                ),
                dmc.Button(
                    id=ids["clear"],
                    children="Clear",
                    variant="light",
                    color="gray",
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
    ]


def virt_cluster_filter_ids(prefix: str) -> dict[str, str]:
    return _ids(prefix)
