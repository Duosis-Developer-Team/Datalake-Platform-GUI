"""LDAP configuration."""

from __future__ import annotations

import os

import dash_mantine_components as dmc
from dash import dcc, html
from dash_iconify import DashIconify

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

    roles = settings_crud.list_roles()
    role_opts = [{"value": str(r["id"]), "label": r.get("name") or str(r["id"])} for r in roles]
    default_role_val = role_opts[0]["value"] if role_opts else ""

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
            dcc.Input(id="ldap-config-id", type="hidden", name="ldap_id", value=str(cid)),
            dmc.SimpleGrid(
                cols=2,
                spacing="md",
                children=[
                    _labeled_input(
                        "name",
                        "Config name",
                        cfg.get("name") if cfg else "default",
                        help_text="Friendly label for this LDAP profile in the UI.",
                        input_id="ldap-field-name",
                    ),
                    _labeled_input(
                        "server_primary",
                        "Primary server",
                        cfg.get("server_primary") if cfg else "",
                        help_text="Hostname or IP of the first directory server (failover uses secondary if set).",
                        input_id="ldap-field-server_primary",
                    ),
                    _labeled_input(
                        "server_secondary",
                        "Secondary server",
                        (cfg.get("server_secondary") or "") if cfg else "",
                        help_text="Optional backup host when the primary is unreachable.",
                        input_id="ldap-field-server_secondary",
                    ),
                    _labeled_input(
                        "port",
                        "Port",
                        str(cfg.get("port") if cfg else 389),
                        help_text="389 for plain LDAP, 636 for LDAPS (SSL).",
                        input_id="ldap-field-port",
                    ),
                    _labeled_input(
                        "bind_dn",
                        "Bind DN",
                        cfg.get("bind_dn") if cfg else "",
                        help_text="Service account DN used to read the directory, e.g. CN=svc-ldap,OU=ServiceAccounts,DC=corp,DC=com.",
                        input_id="ldap-field-bind_dn",
                    ),
                    _labeled_input(
                        "bind_password",
                        "Bind password (leave blank to keep)",
                        "",
                        inp_type="password",
                        help_text="Password for Bind DN; stored encrypted. Leave empty when saving to keep the existing password.",
                        input_id="ldap-field-bind_password",
                    ),
                    _labeled_input(
                        "search_base_dn",
                        "Search base DN",
                        cfg.get("search_base_dn") if cfg else "",
                        help_text="Root DN for searches, e.g. DC=corp,DC=com or a narrower OU for faster queries.",
                        input_id="ldap-field-search_base_dn",
                    ),
                    _labeled_input(
                        "user_search_filter",
                        "User search filter",
                        cfg.get("user_search_filter") if cfg else "(sAMAccountName={username})",
                        help_text="Filter to resolve the user DN at login; {username} is replaced with the typed login name.",
                        input_id="ldap-field-user_search_filter",
                    ),
                    html.Div(
                        [
                            _label_row(
                                "Use SSL (0 or 1)",
                                "1 = LDAPS (port 636 recommended), 0 = cleartext LDAP on the configured port.",
                            ),
                            dcc.Input(
                                id="ldap-field-use_ssl",
                                name="use_ssl",
                                value="1" if (cfg and cfg.get("use_ssl")) else "0",
                                style=_inp(),
                            ),
                            dmc.Text("Tip: use 1 for LDAPS / TLS-wrapped LDAP.", size="xs", c="dimmed", mt=4),
                        ]
                    ),
                ],
            ),
            html.Div(id="ldap-test-feedback"),
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
                    dmc.Button(
                        "Test connection",
                        id="ldap-test-btn",
                        variant="light",
                        color="indigo",
                        leftSection=DashIconify(icon="solar:plug-circle-bold-duotone", width=18),
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
                                _label_row(
                                    "LDAP group DN",
                                    "Distinguished name of the group whose members receive the mapped role.",
                                ),
                                dcc.Input(
                                    name="ldap_group_dn",
                                    placeholder="CN=Group,OU=...",
                                    style=_inp(),
                                ),
                            ],
                        ),
                        html.Div(
                            style={"minWidth": "240px"},
                            children=[
                                _label_row(
                                    "Role",
                                    "Platform role granted to users who are members of this LDAP group.",
                                ),
                                dmc.Select(
                                    id="ldap-mapping-role-select",
                                    data=role_opts,
                                    value=default_role_val or None,
                                    searchable=True,
                                    clearable=False,
                                    style={"width": "100%"},
                                ),
                                dcc.Input(
                                    id="ldap-mapping-role-id",
                                    type="hidden",
                                    name="role_id",
                                    value=default_role_val,
                                ),
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

    # Placeholders so Dash callbacks always find these component ids (hidden when no LDAP config yet).
    mapping_callback_stub = html.Div(
        style={"display": "none"},
        children=[
            dmc.Select(id="ldap-mapping-role-select", data=[], value=None),
            dcc.Input(id="ldap-mapping-role-id", type="hidden", value=""),
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

    shell_children: list = [
        section_header(
            "LDAP integration",
            "Directory servers and group mappings for role assignment.",
            icon="solar:key-minimalistic-bold-duotone",
        ),
        banner,
        env_hint,
        dmc.Paper(p="lg", radius="md", withBorder=True, children=[form]),
    ]
    if not cfg:
        shell_children.append(mapping_callback_stub)
    shell_children.append(mappings)

    return html.Div(settings_page_shell(shell_children))


def _label_row(label: str, help_text: str) -> dmc.Group:
    return dmc.Group(
        gap="xs",
        align="center",
        mb=4,
        children=[
            dmc.Text(label, size="xs", fw=600, c="dimmed"),
            dmc.Tooltip(
                label=help_text,
                children=dmc.ActionIcon(
                    DashIconify(icon="solar:question-circle-bold-duotone", width=16),
                    variant="transparent",
                    size="sm",
                ),
                multiline=True,
                w=320,
            ),
        ],
    )


def _labeled_input(
    name: str,
    label: str,
    value: str,
    *,
    help_text: str,
    inp_type: str = "text",
    input_id: str,
) -> html.Div:
    return html.Div(
        [
            _label_row(label, help_text),
            dcc.Input(
                id=input_id,
                name=name,
                type=inp_type,
                value=value,
                style=_inp(),
            ),
        ]
    )


def _inp():
    return {"width": "100%", "padding": "10px 12px", "borderRadius": "8px", "border": "1px solid #E9ECEF"}


def _th():
    return {"textAlign": "left", "padding": "8px", "borderBottom": "1px solid #e9ecef", "color": "#2B3674"}
