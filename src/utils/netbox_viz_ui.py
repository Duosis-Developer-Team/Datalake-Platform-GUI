"""UI helpers for NetBox/Loki visualization exclusion settings."""

from __future__ import annotations

from typing import Any

import dash_mantine_components as dmc
from dash import html
from dash_iconify import DashIconify

from src.utils.ui_tokens import ON_DIM, ON_SURFACE, PRIMARY, PRIMARY_END, card_style, relative_time, th_left


def role_options(roles: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [{"value": r["role"], "label": r["role"]} for r in roles if r.get("role")]


def compute_exclusion_summary(
    exclusions: list[dict[str, Any]],
    roles: list[dict[str, Any]],
) -> dict[str, int]:
    dc = sum(1 for r in exclusions if str(r.get("view_scope") or "").lower() == "datacenter")
    customer = sum(1 for r in exclusions if str(r.get("view_scope") or "").lower() == "customer")
    catalog = len([r for r in roles if r.get("role")])
    return {
        "datacenter": dc,
        "customer": customer,
        "catalog": catalog,
    }


def filter_exclusions_by_scope(
    exclusions: list[dict[str, Any]],
    scope: str,
    search: str | None = None,
) -> list[dict[str, Any]]:
    scoped = [r for r in exclusions if str(r.get("view_scope") or "").lower() == scope.lower()]
    q = (search or "").strip().lower()
    if not q:
        return scoped
    return [
        r
        for r in scoped
        if q in str(r.get("dimension_value") or "").lower()
        or q in str(r.get("notes") or "").lower()
        or q in str(r.get("updated_by") or "").lower()
    ]


def build_summary_badge_children(summary: dict[str, int]) -> list:
    return [
        dmc.Badge(
            f"Datacenter: {summary['datacenter']} excluded",
            color="indigo",
            variant="light",
            size="lg",
        ),
        dmc.Badge(
            f"Customer: {summary['customer']} excluded",
            color="violet",
            variant="light",
            size="lg",
        ),
        dmc.Badge(
            f"Roles in catalog: {summary['catalog']}",
            color="gray",
            variant="light",
            size="lg",
        ),
    ]


def build_summary_badges(summary: dict[str, int]) -> dmc.Group:
    return dmc.Group(
        id="nbx-summary-badges",
        gap="xs",
        mb="md",
        children=build_summary_badge_children(summary),
    )


def build_impact_info_card() -> dmc.Paper:
    affected = [
        ("Physical Inventory", "solar:box-bold-duotone"),
        ("Network", "solar:transmission-bold-duotone"),
        ("Storage", "solar:database-bold-duotone"),
    ]
    return dmc.Paper(
        p="lg",
        radius="md",
        mb="md",
        style={
            "background": "linear-gradient(135deg, #f6f2ff 0%, #ede8ff 55%, #ffffff 100%)",
            "border": "1px solid rgba(85, 44, 248, 0.12)",
        },
        children=[
            dmc.Group(
                align="flex-start",
                wrap="wrap",
                gap="md",
                children=[
                    dmc.ThemeIcon(
                        DashIconify(icon="solar:server-square-cloud-bold-duotone", width=24, color="#fff"),
                        size="xl",
                        radius="md",
                        variant="filled",
                        color="indigo",
                        style={"background": f"linear-gradient(135deg, {PRIMARY} 0%, {PRIMARY_END} 100%)"},
                    ),
                    dmc.Stack(
                        gap="xs",
                        style={"flex": 1, "minWidth": "220px"},
                        children=[
                            dmc.Text("Where exclusions apply", fw=700, c=ON_SURFACE),
                            dmc.Text(
                                "Excluded device roles are hidden from datacenter or customer dashboards. "
                                "Scopes are independent.",
                                size="sm",
                                c=ON_DIM,
                            ),
                            dmc.Group(
                                gap="xs",
                                wrap="wrap",
                                mt="xs",
                                children=[
                                    *[
                                        dmc.Badge(
                                            dmc.Group(
                                                gap=4,
                                                children=[
                                                    DashIconify(icon=icon, width=14),
                                                    label,
                                                ],
                                            ),
                                            color="indigo",
                                            variant="light",
                                            size="md",
                                        )
                                        for label, icon in affected
                                    ],
                                    dmc.Badge(
                                        dmc.Group(
                                            gap=4,
                                            children=[
                                                DashIconify(icon="solar:map-point-bold-duotone", width=14),
                                                "Floor Map — not affected",
                                            ],
                                        ),
                                        color="gray",
                                        variant="outline",
                                        size="md",
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


def build_exclusion_table(rows: list[dict[str, Any]], scope: str) -> html.Div:
    if not rows:
        return dmc.Alert(
            color="blue",
            variant="light",
            title="No exclusions configured",
            children="Devices of all roles are visible in dashboards for this scope.",
        )

    body_rows = []
    for r in rows:
        rid = int(r.get("id") or 0)
        role = str(r.get("dimension_value") or "")
        notes = str(r.get("notes") or "").strip() or "—"
        updated_by = str(r.get("updated_by") or "").strip() or "—"
        updated_at = relative_time(r.get("updated_at"))

        body_rows.append(
            html.Tr(
                style={"borderBottom": "1px solid #eef1f4"},
                children=[
                    html.Td(
                        dmc.Badge(role, color="indigo", variant="light", size="sm"),
                        style={"padding": "10px 12px"},
                    ),
                    html.Td(
                        dmc.Text(notes, size="sm", c="dimmed" if notes == "—" else ON_SURFACE),
                        style={"padding": "10px 12px", "maxWidth": "280px"},
                    ),
                    html.Td(
                        dmc.Stack(
                            gap=0,
                            children=[
                                dmc.Text(updated_by, size="sm"),
                                dmc.Text(updated_at, size="xs", c="dimmed"),
                            ],
                        ),
                        style={"padding": "10px 12px"},
                    ),
                    html.Td(
                        dmc.ActionIcon(
                            DashIconify(icon="tabler:trash", width=16),
                            id={"type": "nbx-del", "rid": rid, "scope": scope},
                            color="red",
                            variant="light",
                            size="sm",
                        ),
                        style={"padding": "10px 12px", "textAlign": "right"},
                    ),
                ],
            )
        )

    return html.Div(
        style={"overflowX": "auto"},
        children=[
            html.Table(
                style={"width": "100%", "borderCollapse": "collapse", "fontSize": "13px"},
                children=[
                    html.Thead(
                        html.Tr(
                            [
                                html.Th("Device role", style=th_left()),
                                html.Th("Notes", style=th_left()),
                                html.Th("Updated", style=th_left()),
                                html.Th("", style={**th_left(), "width": "48px"}),
                            ]
                        )
                    ),
                    html.Tbody(body_rows),
                ],
            )
        ],
    )


def scope_table_count_label(rows: list[dict[str, Any]], search: str | None) -> str:
    total = len(rows)
    q = (search or "").strip()
    if not total:
        return "No exclusions" if not q else "No matches"
    if q:
        return f"{total} match(es)"
    return f"{total} exclusion(s)"
