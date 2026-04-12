"""Role management — edit role_permissions matrix (single role at a time)."""

from __future__ import annotations

from collections import defaultdict
from urllib.parse import parse_qs

import dash_mantine_components as dmc
from dash import dcc, html
from dash_iconify import DashIconify

from src.services import admin_client as settings_crud
from src.utils.ui_tokens import ON_SURFACE, PRIMARY, section_header, settings_page_shell


def build_layout(search: str | None = None) -> html.Div:
    roles = settings_crud.list_roles()
    perms = settings_crud.list_permissions_flat()

    qs = parse_qs((search or "").lstrip("?"))
    rid_s = (qs.get("role_id") or [""])[0].strip()
    try:
        selected_rid = int(rid_s)
    except ValueError:
        selected_rid = 0

    role_by_id = {int(r["id"]): r for r in roles}
    if selected_rid not in role_by_id and roles:
        selected_rid = int(roles[0]["id"])

    left_cards = []
    for r in roles:
        rid = int(r["id"])
        active = rid == selected_rid
        left_cards.append(
            dmc.Paper(
                p="md",
                radius="md",
                withBorder=True,
                style={
                    "border": f"2px solid {PRIMARY}" if active else "1px solid rgba(171,173,176,0.25)",
                    "background": "rgba(85, 44, 248, 0.04)" if active else "#fff",
                },
                children=[
                    dmc.Group(
                        justify="space-between",
                        align="flex-start",
                        wrap="nowrap",
                        children=[
                            dmc.Anchor(
                                href=f"/settings/iam/roles?role_id={rid}",
                                underline=False,
                                style={"flex": 1, "minWidth": 0},
                                children=dmc.Group(
                                    gap="sm",
                                    children=[
                                        dmc.ThemeIcon(
                                            DashIconify(icon="solar:shield-user-bold-duotone", width=20),
                                            variant="light",
                                            color="indigo",
                                            radius="md",
                                        ),
                                        dmc.Stack(
                                            gap=2,
                                            style={"minWidth": 0, "flex": 1},
                                            children=[
                                                dmc.Text(str(r["name"]), fw=800, size="sm", c=ON_SURFACE),
                                                dmc.Text(
                                                    str(r.get("description") or ""),
                                                    size="xs",
                                                    c="dimmed",
                                                    lineClamp=1,
                                                ),
                                            ],
                                        ),
                                    ],
                                ),
                            ),
                            dmc.Group(
                                gap="xs",
                                wrap="nowrap",
                                align="center",
                                children=[
                                    dmc.Badge(
                                        "system" if r.get("is_system") else "custom",
                                        size="xs",
                                        variant="light",
                                        color="gray",
                                    ),
                                    dmc.Button(
                                        "Edit",
                                        id={"type": "iam-role-edit", "rid": rid},
                                        size="xs",
                                        variant="light",
                                        color="indigo",
                                    ),
                                ],
                            ),
                        ],
                    )
                ],
            )
        )

    matrix_body: list = []
    if selected_rid:
        rp = {int(x["permission_id"]): x for x in settings_crud.get_role_permission_rows(selected_rid)}
        by_rt: dict[str, list] = defaultdict(list)
        for p in perms[:100]:
            rt = str(p.get("resource_type") or "other")
            by_rt[rt].append(p)

        acc_items = []
        for rt, plist in sorted(by_rt.items(), key=lambda x: x[0]):
            label = {
                "page": "Page access",
                "section": "Sections",
                "action": "Actions",
                "config": "Configuration",
                "grp": "Groups",
            }.get(rt, rt.replace("_", " ").title())

            rows = []
            for p in plist:
                pid = int(p["id"])
                row = rp.get(pid) or {}
                help_txt = _permission_help_text(p)
                rows.append(
                    html.Tr(
                        style={"borderTop": "1px solid #eef1f4"},
                        children=[
                            html.Td(
                                dmc.Stack(
                                    gap=2,
                                    children=[
                                        dmc.Text(str(p.get("name") or p["code"]), size="sm", fw=500),
                                        dmc.Text(str(p["code"]), size="xs", c="dimmed"),
                                        dmc.Text(help_txt, size="xs", c="dimmed"),
                                    ],
                                ),
                                style={"padding": "10px 12px", "maxWidth": "420px"},
                            ),
                            html.Td(
                                _cb(pid, "v", bool(row.get("can_view"))),
                                style={"textAlign": "center", "padding": "8px"},
                            ),
                            html.Td(
                                _cb(pid, "e", bool(row.get("can_edit"))),
                                style={"textAlign": "center", "padding": "8px"},
                            ),
                            html.Td(
                                _cb(pid, "x", bool(row.get("can_export"))),
                                style={"textAlign": "center", "padding": "8px"},
                            ),
                        ],
                    )
                )

            acc_items.append(
                dmc.AccordionItem(
                    value=rt,
                    children=[
                        dmc.AccordionControl(
                            dmc.Group(
                                gap="sm",
                                wrap="nowrap",
                                children=[
                                    DashIconify(icon="solar:widget-5-bold-duotone", width=18, color=PRIMARY),
                                    dmc.Text(label, fw=700, size="sm", c=ON_SURFACE),
                                    dmc.Badge(f"{len(plist)}", size="xs", variant="light", color="gray"),
                                ],
                            )
                        ),
                        dmc.AccordionPanel(
                            p="xs",
                            children=[
                                dmc.Paper(
                                    p="xs",
                                    radius="md",
                                    withBorder=True,
                                    children=[
                                        html.Table(
                                            style={"width": "100%", "borderCollapse": "collapse"},
                                            children=[
                                                html.Tr(
                                                    [
                                                        html.Th("Permission", style=_th_left()),
                                                        html.Th("View", style=_th_center()),
                                                        html.Th("Edit", style=_th_center()),
                                                        html.Th("Export", style=_th_center()),
                                                    ]
                                                ),
                                                *rows,
                                            ],
                                        )
                                    ],
                                )
                            ],
                        ),
                    ],
                )
            )

        matrix_body = [
            dmc.Accordion(
                children=acc_items,
                multiple=True,
                variant="separated",
                radius="md",
                chevronPosition="right",
                value=list(by_rt.keys()),
                style={"width": "100%"},
            )
        ]

        sel = role_by_id.get(selected_rid, {})
        form = html.Div(
            children=[
                dcc.Store(id="role-matrix-role-id", data=selected_rid),
                dmc.Group(
                    justify="space-between",
                    mb="md",
                    children=[
                        dmc.Stack(
                            gap=4,
                            children=[
                                dmc.Text(f"Role: {sel.get('name', '')}", fw=800, c=ON_SURFACE),
                                dmc.Text(
                                    "Changes apply to this role only. Maximum 100 permission rows shown.",
                                    size="xs",
                                    c="dimmed",
                                ),
                            ],
                        ),
                        dmc.Button(
                            "Save matrix",
                            id="save-role-matrix-btn",
                            leftSection=DashIconify(icon="solar:diskette-bold-duotone", width=18),
                            variant="filled",
                            color="indigo",
                            styles={
                                "root": {
                                    "background": "linear-gradient(135deg, #552cf8 0%, #a092ff 100%)",
                                    "border": "none",
                                    "transition": "opacity 0.18s ease",
                                }
                            },
                        ),
                    ],
                ),
                html.Div(id="role-matrix-feedback", style={"marginBottom": "12px"}),
                html.Div(matrix_body),
            ],
        )
    else:
        form = dmc.Alert("No roles defined.", color="yellow")

    layout_grid = dmc.Grid(
        gutter="lg",
        children=[
            dmc.GridCol(
                span=4,
                children=[
                    dmc.Text("Defined roles", fw=700, mb="sm", c=ON_SURFACE),
                    dmc.Stack(gap="sm", children=left_cards),
                ],
            ),
            dmc.GridCol(span=8, children=[form]),
        ],
    )

    return html.Div(
        [
            dcc.Store(id="iam-role-edit-id-store", data=None),
            dcc.Store(id="iam-role-edit-is-system-store", data=False),
            dmc.Modal(
                title="Edit role",
                id="iam-role-edit-modal",
                opened=False,
                children=[
                    dmc.Text("Name", size="xs", fw=600, c="dimmed", mb=4),
                    dcc.Input(id="iam-role-edit-name", type="text", style=_role_input_style()),
                    dmc.Text("Description", size="xs", fw=600, c="dimmed", mb=4, mt="sm"),
                    dcc.Textarea(
                        id="iam-role-edit-description",
                        style={**_role_input_style(), "minHeight": "80px", "resize": "vertical"},
                    ),
                    html.Div(id="iam-role-edit-feedback", style={"marginTop": "8px"}),
                    dmc.Group(
                        gap="sm",
                        mt="md",
                        justify="space-between",
                        children=[
                            dmc.Button(
                                "Delete role",
                                id="iam-role-delete-btn",
                                variant="outline",
                                color="red",
                                size="sm",
                            ),
                            dmc.Group(
                                gap="sm",
                                children=[
                                    dmc.Button("Cancel", id="iam-role-edit-cancel", variant="default", color="gray"),
                                    dmc.Button("Save", id="iam-role-edit-save", variant="filled", color="indigo"),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
            settings_page_shell(
                [
                    section_header(
                        "Role configuration",
                        "Assign view, edit, and export rights per permission node.",
                        icon="solar:shield-check-bold-duotone",
                    ),
                    layout_grid,
                ]
            ),
        ]
    )


def _permission_help_text(p: dict) -> str:
    d = (p.get("description") or "").strip()
    if d:
        return d
    return f"Controls access to {p.get('name') or p.get('code', 'this resource')}."


def _role_input_style():
    return {
        "width": "100%",
        "padding": "10px 12px",
        "borderRadius": "8px",
        "border": "1px solid #e9ecef",
        "fontSize": "14px",
    }


def _cb(pid: int, col: str, checked: bool) -> dcc.Checklist:
    """Single-cell checkbox rendered as dcc.Checklist for Dash compatibility."""
    return dcc.Checklist(
        id={"type": "perm-cb", "pid": pid, "col": col},
        options=[{"label": "", "value": "on"}],
        value=["on"] if checked else [],
        inputStyle={
            "width": "16px",
            "height": "16px",
            "cursor": "pointer",
            "accentColor": "#552cf8",
        },
        labelStyle={"margin": "0", "padding": "0"},
        style={"display": "flex", "justifyContent": "center", "alignItems": "center"},
    )


def _th_left():
    return {
        "textAlign": "left",
        "padding": "8px 12px",
        "fontSize": "11px",
        "textTransform": "uppercase",
        "color": "#6c757d",
        "fontWeight": 600,
    }


def _th_center():
    return {
        "textAlign": "center",
        "padding": "8px",
        "fontSize": "11px",
        "textTransform": "uppercase",
        "color": "#6c757d",
        "fontWeight": 600,
    }
