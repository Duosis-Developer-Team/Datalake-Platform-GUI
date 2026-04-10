"""Role management — edit role_permissions matrix."""

from __future__ import annotations

import dash_mantine_components as dmc
from dash import html

from src.auth import settings_crud


def build_layout() -> html.Div:
    roles = settings_crud.list_roles()
    perms = settings_crud.list_permissions_flat()

    forms = []
    for r in roles:
        rid = int(r["id"])
        rp = {int(x["permission_id"]): x for x in settings_crud.get_role_permission_rows(rid)}
        check_rows = []
        for p in perms[:100]:
            pid = int(p["id"])
            row = rp.get(pid) or {}
            check_rows.append(
                html.Tr(
                    [
                        html.Td(str(p["code"]), style={"fontSize": "11px", "padding": "4px"}),
                        html.Td(
                            html.Input(
                                type="checkbox",
                                name=f"v_{pid}",
                                **({"checked": "checked"} if row.get("can_view") else {}),
                            )
                        ),
                        html.Td(
                            html.Input(
                                type="checkbox",
                                name=f"e_{pid}",
                                **({"checked": "checked"} if row.get("can_edit") else {}),
                            )
                        ),
                        html.Td(
                            html.Input(
                                type="checkbox",
                                name=f"x_{pid}",
                                **({"checked": "checked"} if row.get("can_export") else {}),
                            )
                        ),
                    ]
                )
            )
        forms.append(
            html.Form(
                method="POST",
                action="/auth/settings/role-matrix",
                children=[
                    html.Input(type="hidden", name="role_id", value=str(rid)),
                    dmc.Text(f"Role: {r['name']}", fw=700, mb="xs", size="sm"),
                    html.Table(
                        [
                            html.Tr(
                                [
                                    html.Th("Permission", style={"textAlign": "left"}),
                                    html.Th("V"),
                                    html.Th("E"),
                                    html.Th("X"),
                                ]
                            ),
                            *check_rows,
                        ],
                        style={"width": "100%", "fontSize": "12px", "marginBottom": "16px"},
                    ),
                    html.Button(
                        "Save " + str(r["name"]),
                        type="submit",
                        style={
                            "padding": "8px 14px",
                            "background": "#4318FF",
                            "color": "#fff",
                            "border": "none",
                            "borderRadius": "8px",
                            "cursor": "pointer",
                            "marginBottom": "28px",
                        },
                    ),
                ],
            )
        )

    return html.Div(
        [
            dmc.Title("Roles", order=3, mb="sm", c="#2B3674"),
            dmc.Text(
                "Update view/edit/export per permission (up to 100 nodes shown). Submit each role separately.",
                size="sm",
                c="dimmed",
                mb="md",
            ),
            html.Div(forms),
        ]
    )
