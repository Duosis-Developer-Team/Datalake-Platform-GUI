"""Integrations — NetBox/Loki visualization exclusions (gui_netbox_viz_exclusion)."""

from __future__ import annotations

from dash import dcc, html
import dash_mantine_components as dmc
from dash_iconify import DashIconify

from src.services import api_client as api
from src.utils.netbox_viz_ui import (
    build_exclusion_table,
    build_impact_info_card,
    build_summary_badges,
    compute_exclusion_summary,
    filter_exclusions_by_scope,
    role_options,
    scope_table_count_label,
)
from src.utils.ui_tokens import card_style, section_header, settings_page_shell


def _add_exclusion_card(scope: str, label: str, role_data: list[dict[str, str]]) -> dmc.Paper:
    return dmc.Paper(
        children=[
            dmc.Group(
                justify="space-between",
                align="center",
                mb="sm",
                children=[
                    dmc.Text("Add exclusion", fw=700, size="sm"),
                    dmc.Badge(label.capitalize(), color="indigo", variant="light", size="sm"),
                ],
            ),
            dmc.Grid(
                gutter="sm",
                children=[
                    dmc.GridCol(
                        span={"base": 12, "md": 8},
                        children=dmc.MultiSelect(
                            id=f"nbx-roles-{scope}",
                            label="Device roles to exclude",
                            placeholder="Search and select roles…",
                            data=role_data,
                            searchable=True,
                            clearable=True,
                            size="sm",
                            leftSection=DashIconify(icon="solar:magnifer-linear", width=16, color="#A3AED0"),
                        ),
                    ),
                    dmc.GridCol(
                        span={"base": 12, "md": 4},
                        children=dmc.TextInput(
                            id=f"nbx-notes-{scope}",
                            label="Notes (optional)",
                            placeholder="Reason or ticket ref",
                            size="sm",
                        ),
                    ),
                    dmc.GridCol(
                        span={"base": 12, "md": 12},
                        children=dmc.Group(
                            gap="sm",
                            children=[
                                dmc.Button(
                                    f"Exclude selected roles",
                                    id=f"nbx-save-{scope}",
                                    size="sm",
                                    variant="gradient",
                                    gradient={"from": "indigo", "to": "violet", "deg": 105},
                                    leftSection=DashIconify(icon="solar:add-circle-bold-duotone", width=18),
                                ),
                            ],
                        ),
                    ),
                ],
            ),
            html.Div(id=f"nbx-msg-{scope}", style={"marginTop": "8px"}),
        ],
        **card_style(),
        mb="md",
    )


def _active_exclusions_card(scope: str, label: str, exclusions: list[dict]) -> dmc.Paper:
    scoped = filter_exclusions_by_scope(exclusions, scope)
    count_label = scope_table_count_label(scoped, None)

    return dmc.Paper(
        p=0,
        radius="md",
        withBorder=True,
        style=card_style()["style"],
        children=[
            html.Div(
                style={"padding": "16px 20px", "borderBottom": "1px solid #eef1f4"},
                children=[
                    dmc.Group(
                        justify="space-between",
                        align="flex-end",
                        wrap="wrap",
                        gap="sm",
                        children=[
                            dmc.Stack(
                                gap=2,
                                children=[
                                    dmc.Text(f"Active exclusions — {label}", fw=700, size="sm"),
                                    dmc.Text(
                                        id=f"nbx-table-count-{scope}",
                                        size="xs",
                                        c="dimmed",
                                        children=count_label,
                                    ),
                                ],
                            ),
                            dmc.TextInput(
                                id=f"nbx-search-{scope}",
                                placeholder="Filter by role, notes, user…",
                                leftSection=DashIconify(icon="solar:magnifer-linear", width=16, color="#A3AED0"),
                                size="sm",
                                style={"width": "min(320px, 100%)"},
                            ),
                        ],
                    ),
                ],
            ),
            html.Div(
                id=f"nbx-table-{scope}",
                style={"padding": "12px 16px 16px"},
                children=build_exclusion_table(scoped, scope),
            ),
        ],
    )


def _scope_panel(
    scope: str,
    label: str,
    role_data: list[dict[str, str]],
    exclusions: list[dict],
) -> dmc.TabsPanel:
    return dmc.TabsPanel(
        value=scope,
        children=[
            _add_exclusion_card(scope, label, role_data),
            _active_exclusions_card(scope, label, exclusions),
        ],
    )


def build_layout(search: str | None = None) -> html.Div:
    _ = search
    exclusions = api.get_netbox_viz_exclusions()
    roles = api.get_netbox_device_roles()
    role_data = role_options(roles)
    summary = compute_exclusion_summary(exclusions, roles)

    return html.Div(
        settings_page_shell(
            [
                dcc.Store(id="nbx-exclusions-store", data=exclusions),
                dcc.Store(id="nbx-delete-pending", data=None),
                section_header(
                    "NetBox / Loki visualization filters",
                    "Choose device roles to exclude from dashboards and aggregations. "
                    "Datacenter and customer scopes are independent.",
                    icon="solar:server-square-cloud-bold-duotone",
                ),
                build_impact_info_card(),
                build_summary_badges(summary),
                dmc.Paper(
                    p="md",
                    radius="md",
                    withBorder=True,
                    style=card_style()["style"],
                    children=[
                        dmc.Tabs(
                            value="datacenter",
                            children=[
                                dmc.TabsList(
                                    children=[
                                        dmc.TabsTab(
                                            dmc.Group(
                                                gap=6,
                                                children=[
                                                    DashIconify(icon="solar:server-path-bold-duotone", width=16),
                                                    "Datacenter",
                                                ],
                                            ),
                                            value="datacenter",
                                        ),
                                        dmc.TabsTab(
                                            dmc.Group(
                                                gap=6,
                                                children=[
                                                    DashIconify(icon="solar:users-group-rounded-bold-duotone", width=16),
                                                    "Customer",
                                                ],
                                            ),
                                            value="customer",
                                        ),
                                    ]
                                ),
                                _scope_panel("datacenter", "datacenter", role_data, exclusions),
                                _scope_panel("customer", "customer", role_data, exclusions),
                            ],
                        ),
                        html.Div(id="nbx-del-msg", style={"marginTop": "8px"}),
                    ],
                ),
                dmc.Modal(
                    title="Remove exclusion",
                    id="nbx-delete-modal",
                    opened=False,
                    children=[
                        dmc.Text(
                            id="nbx-delete-modal-body",
                            size="sm",
                            children="Remove this device role from the exclusion list?",
                        ),
                        dmc.Group(
                            justify="flex-end",
                            gap="sm",
                            mt="md",
                            children=[
                                dmc.Button("Cancel", id="nbx-delete-cancel", variant="subtle", color="gray"),
                                dmc.Button(
                                    "Remove",
                                    id="nbx-delete-confirm",
                                    color="red",
                                    variant="filled",
                                    leftSection=DashIconify(icon="tabler:trash", width=16),
                                ),
                            ],
                        ),
                    ],
                ),
            ]
        )
    )
