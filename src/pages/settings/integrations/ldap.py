"""LDAP configuration."""

from __future__ import annotations

import os

import dash_mantine_components as dmc
from dash import dcc, html

from src.services import admin_client as settings_crud
from src.utils.ui_tokens import (
    html_submit_button_gradient,
    html_submit_button_light,
    section_header,
    settings_page_shell,
)


def build_layout(search: str | None = None) -> html.Div:
    cfgs = settings_crud.list_ldap_configs()
    cfg = cfgs[0] if cfgs else None
    cid = int(cfg["id"]) if cfg else ""

    mapping_rows = []
    if cfg:
        for m in settings_crud.list_ldap_group_mappings(int(cfg["id"])):
            mapping_rows.append(
                html.Tr(
                    style={"borderBottom": "1px solid #eef1f4"},
                    children=[
                        html.Td(str(m.get("ldap_group_dn", ""))[:120], style={"fontSize": "12px"}),
                        html.Td(str(m.get("role_name", ""))),
                        html.Td(
                            html.Form(
                                method="POST",
                                action="/auth/settings/ldap-mapping-delete",
                                style={"display": "inline"},
                                children=[
                                    dcc.Input(type="hidden", name="mapping_id", value=str(m["id"])),
                                    html_submit_button_light("Remove", scheme="red", small=True),
                                ],
                            )
                        ),
                    ],
                )
            )

    banner = None
    if cfg:
        active = bool(cfg.get("is_active"))
        banner = dmc.Alert(
            "This configuration is active for interactive LDAP login."
            if active
            else "This configuration exists but is marked inactive.",
            color="green" if active else "orange",
            variant="light",
            mb="md",
        )

    env_hint = None
    ldap_host = os.environ.get("LDAP_HOST")
    if ldap_host:
        env_hint = dmc.Text(
            f"Note: LDAP_HOST is set in environment ({ldap_host}) — deployment may use it outside this form.",
            size="xs",
            c="dimmed",
            mb="sm",
        )

    form = html.Form(
        method="POST",
        action="/auth/settings/ldap-save",
        children=[
            dcc.Input(type="hidden", name="ldap_id", value=str(cid)),
            dmc.SimpleGrid(
                cols=2,
                spacing="md",
                children=[
                    _field("name", "Config name", cfg.get("name") if cfg else "default"),
                    _field("server_primary", "Primary server", cfg.get("server_primary") if cfg else ""),
                    _field(
                        "server_secondary",
                        "Secondary server",
                        (cfg.get("server_secondary") or "") if cfg else "",
                    ),
                    _field("port", "Port", str(cfg.get("port") if cfg else 389)),
                    _field("bind_dn", "Bind DN", cfg.get("bind_dn") if cfg else ""),
                    _field("bind_password", "Bind password (leave blank to keep)", "", "password"),
                    _field("search_base_dn", "Search base", cfg.get("search_base_dn") if cfg else ""),
                    _field(
                        "user_search_filter",
                        "User filter",
                        cfg.get("user_search_filter") if cfg else "(sAMAccountName={username})",
                    ),
                    html.Div(
                        [
                            dmc.Text("Use SSL (0 or 1)", size="xs", fw=600, c="dimmed", mb=4),
                            dcc.Input(
                                name="use_ssl",
                                value="1" if (cfg and cfg.get("use_ssl")) else "0",
                                style=_inp(),
                            ),
                            dmc.Text("Tip: use 1 for LDAPS / TLS-wrapped LDAP.", size="xs", c="dimmed", mt=4),
                        ]
                    ),
                ],
            ),
            dmc.Group(
                gap="sm",
                mt="md",
                align="center",
                wrap="wrap",
                children=[
                    html_submit_button_gradient(
                        "Save LDAP configuration",
                        icon="solar:diskette-bold-duotone",
                    ),
                ],
            ),
        ],
    )

    mapping_form = None
    if cfg:
        mapping_form = html.Form(
            method="POST",
            action="/auth/settings/ldap-mapping-add",
            style={"padding": "16px", "borderBottom": "1px solid #eef1f4"},
            children=[
                dcc.Input(type="hidden", name="ldap_config_id", value=str(cid)),
                dmc.Group(
                    align="flex-end",
                    gap="sm",
                    wrap="wrap",
                    children=[
                        html.Div(
                            style={"flex": "2", "minWidth": "200px"},
                            children=[
                                dmc.Text("LDAP group DN", size="xs", fw=600, c="dimmed", mb=4),
                                dcc.Input(
                                    name="ldap_group_dn",
                                    placeholder="CN=Group,OU=...",
                                    style=_inp(),
                                ),
                            ],
                        ),
                        html.Div(
                            style={"width": "120px"},
                            children=[
                                dmc.Text("Role id", size="xs", fw=600, c="dimmed", mb=4),
                                dcc.Input(name="role_id", placeholder="id", style=_inp()),
                            ],
                        ),
                        html_submit_button_light(
                            "Add mapping",
                            scheme="indigo",
                            style_extra={"marginTop": "24px", "alignSelf": "flex-end"},
                        ),
                    ],
                ),
            ],
        )

    mappings = (
        dmc.Paper(
            p=0,
            radius="md",
            withBorder=True,
            mt="lg",
            children=[
                html.Div(
                    style={"padding": "16px 20px", "borderBottom": "1px solid #eef1f4"},
                    children=dmc.Text("Group → role mappings", fw=700),
                ),
                mapping_form,
                html.Div(
                    style={"overflowX": "auto", "padding": "0 16px 16px"},
                    children=[
                        html.Table(
                            [
                                html.Tr(
                                    [
                                        html.Th("Group DN", style=_th()),
                                        html.Th("Role", style=_th()),
                                        html.Th("", style=_th()),
                                    ]
                                ),
                                *mapping_rows,
                            ],
                            style={"width": "100%", "fontSize": "13px"},
                        )
                    ],
                ),
            ],
        )
        if cfg
        else dmc.Alert("Save a primary LDAP configuration to manage mappings.", color="blue", variant="light", mt="lg")
    )

    return html.Div(
        settings_page_shell(
            [
                section_header(
                    "LDAP integration",
                    "Directory servers and group mappings for role assignment.",
                    icon="solar:key-minimalistic-bold-duotone",
                ),
                banner,
                env_hint,
                dmc.Paper(p="lg", radius="md", withBorder=True, children=[form]),
                mappings,
            ]
        )
    )


def _field(name: str, label: str, value: str, inp_type: str = "text"):
    return html.Div(
        [
            dmc.Text(label, size="xs", fw=600, c="dimmed", mb=4),
            dcc.Input(name=name, type=inp_type, value=value, style=_inp()),
        ]
    )


def _inp():
    return {"width": "100%", "padding": "10px 12px", "borderRadius": "8px", "border": "1px solid #E9ECEF"}


def _th():
    return {"textAlign": "left", "padding": "8px", "borderBottom": "1px solid #e9ecef", "color": "#2B3674"}
