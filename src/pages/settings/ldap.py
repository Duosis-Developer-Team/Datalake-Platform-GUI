"""LDAP configuration."""

from __future__ import annotations

import dash_mantine_components as dmc
from dash import dcc, html

from src.auth import settings_crud


def build_layout() -> html.Div:
    cfgs = settings_crud.list_ldap_configs()
    cfg = cfgs[0] if cfgs else None
    cid = int(cfg["id"]) if cfg else ""

    mapping_rows = []
    if cfg:
        for m in settings_crud.list_ldap_group_mappings(int(cfg["id"])):
            mapping_rows.append(
                html.Tr(
                    [
                        html.Td(str(m.get("ldap_group_dn", ""))[:80]),
                        html.Td(str(m.get("role_name", ""))),
                        html.Td(
                            html.Form(
                                method="POST",
                                action="/auth/settings/ldap-mapping-delete",
                                style={"display": "inline"},
                                children=[
                                    dcc.Input(type="hidden", name="mapping_id", value=str(m["id"])),
                                    html.Button("Remove", type="submit", style={"fontSize": "11px"}),
                                ],
                            )
                        ),
                    ]
                )
            )

    return html.Div(
        [
            dmc.Title("LDAP", order=3, mb="sm", c="#2B3674"),
            html.Form(
                method="POST",
                action="/auth/settings/ldap-save",
                style={"padding": "16px", "border": "1px solid #E9ECEF", "borderRadius": "12px", "marginBottom": "16px"},
                children=[
                    dcc.Input(type="hidden", name="ldap_id", value=str(cid)),
                    dmc.SimpleGrid(
                        cols=2,
                        children=[
                            _field("name", "Config name", cfg.get("name") if cfg else "default"),
                            _field("server_primary", "Primary server", cfg.get("server_primary") if cfg else ""),
                            _field("server_secondary", "Secondary server", cfg.get("server_secondary") or ""),
                            _field("port", "Port", str(cfg.get("port") if cfg else 389)),
                            _field("bind_dn", "Bind DN", cfg.get("bind_dn") if cfg else ""),
                            _field("bind_password", "Bind password (leave blank to keep)", "", "password"),
                            _field("search_base_dn", "Search base", cfg.get("search_base_dn") if cfg else ""),
                            _field("user_search_filter", "User filter", cfg.get("user_search_filter") if cfg else "(sAMAccountName={username})"),
                            _field("use_ssl", "Use SSL (0 or 1)", "1" if (cfg and cfg.get("use_ssl")) else "0"),
                        ],
                    ),
                    html.Button(
                        "Save LDAP config",
                        type="submit",
                        style={
                            "marginTop": "12px",
                            "padding": "8px 16px",
                            "background": "#4318FF",
                            "color": "#fff",
                            "border": "none",
                            "borderRadius": "8px",
                            "cursor": "pointer",
                        },
                    ),
                ],
            ),
            dmc.Text("Group → role mappings", fw=600, mb="xs", mt="lg"),
            html.Form(
                method="POST",
                action="/auth/settings/ldap-mapping-add",
                style={"marginBottom": "16px"},
                children=[
                    dcc.Input(type="hidden", name="ldap_config_id", value=str(cid)),
                    dcc.Input(name="ldap_group_dn", placeholder="CN=Group,OU=...", style={"width": "60%", "marginRight": "8px"}),
                    dcc.Input(name="role_id", placeholder="role id", style={"width": "80px", "marginRight": "8px"}),
                    html.Button("Add mapping", type="submit"),
                ],
            ),
            html.Table(
                [html.Tr([html.Th("Group DN"), html.Th("Role"), html.Th("")]), *mapping_rows],
                style={"width": "100%", "fontSize": "12px"},
            ),
        ]
    )


def _field(name: str, label: str, value: str, inp_type: str = "text"):
    return html.Div(
        [
            dmc.Text(label, size="xs", c="dimmed", mb=4),
            dcc.Input(name=name, type=inp_type, value=value, style={"width": "100%", "padding": "8px"}),
        ]
    )
