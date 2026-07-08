"""Integrations — Internal (Bulutistan) source mappings.

Mirror of the Customer aliases editor, scoped to a single reserved account
(crm_accountid="INTERNAL"). Same mapping logic / same backend table
(gui_crm_customer_source_mapping); this side captures Bulutistan's own
(internal) resources so they can be separated from real customer resources.

Uses the shared editor builders from crm_aliases with prefix="internal-alias"
so its component ids never collide with the Customer aliases page.
"""
from __future__ import annotations

import dash_mantine_components as dmc
from dash import dcc, html
from dash_iconify import DashIconify

from src.pages.settings.integrations.crm_aliases import build_editor_shell
from src.utils.crm_source_mapping_ui import (
    UI_COLUMNS,
    build_editor_state,
    compute_coverage,
)
from src.utils.ui_tokens import ON_SURFACE

PREFIX = "internal-alias"

INTERNAL_ACCOUNT_ID = "INTERNAL"
INTERNAL_ACCOUNT_NAME = "Bulutistan (Internal)"


def _default_internal_alias() -> dict:
    return {
        "crm_accountid": INTERNAL_ACCOUNT_ID,
        "crm_account_name": INTERNAL_ACCOUNT_NAME,
        "notes": "",
        "source": "internal",
        "source_mappings": [],
    }


def summary_strip(internal_alias: dict) -> dmc.Group:
    mappings = internal_alias.get("source_mappings") or []
    covered, total = compute_coverage(mappings)
    filled = len([m for m in mappings if str(m.get("match_value") or "").strip()])
    return dmc.Group(
        gap="xs",
        mb="md",
        children=[
            dmc.Badge("Bulutistan (Internal)", color="teal", variant="light", size="lg"),
            dmc.Badge(f"Coverage: {covered}/{total}", color="indigo", variant="light", size="lg"),
            dmc.Badge(
                f"Mappings: {filled}",
                color="teal" if filled else "gray",
                variant="light",
                size="lg",
            ),
        ],
    )


def build_layout(search: str | None = None) -> html.Div:
    _ = search
    return html.Div(
        id="internal-alias-page-root",
        style={"padding": "30px"},
        children=[
            dcc.Loading(
                type="circle",
                children=dmc.Stack(
                    gap="md",
                    children=[
                        dmc.Skeleton(height=32, width="45%"),
                        dmc.Skeleton(height=18, width="70%"),
                        dmc.Skeleton(height=240),
                    ],
                ),
            ),
        ],
    )


def build_internal_content(
    internal_alias: dict | None,
    *,
    load_error: bool = False,
) -> html.Div:
    alias = internal_alias or _default_internal_alias()
    editor_state = build_editor_state(alias)
    open_sections = [UI_COLUMNS[0][0]]

    if load_error:
        banner = dmc.Alert(
            color="red",
            title="Internal aliases unavailable",
            children="Could not load Internal mappings from customer-api. Verify service health.",
        )
    else:
        banner = dmc.Text(
            "Bulutistan'ın kendi (internal) kaynaklarını tanımlayın — Customer aliases ile birebir aynı mantık.",
            size="sm",
            c="dimmed",
            mb="sm",
        )

    editor_paper = dmc.Paper(
        p="lg",
        radius="md",
        withBorder=True,
        style={"maxWidth": "760px"},
        children=[
            dmc.Group(
                justify="space-between",
                align="center",
                mb="md",
                wrap="nowrap",
                children=[
                    dmc.Stack(
                        gap=2,
                        children=[
                            dmc.Text("Internal (Bulutistan)", fw=700, c=ON_SURFACE),
                            dmc.Text(INTERNAL_ACCOUNT_ID, size="xs", c="dimmed"),
                        ],
                    ),
                    dmc.ThemeIcon(
                        size="lg",
                        variant="light",
                        color="teal",
                        radius="md",
                        children=DashIconify(icon="solar:server-2-bold-duotone", width=20),
                    ),
                ],
            ),
            html.Div(
                id="internal-alias-editor-panel",
                children=build_editor_shell(editor_state, open_sections=open_sections, prefix=PREFIX),
            ),
        ],
    )

    return html.Div(
        style={"padding": "30px"},
        children=[
            dmc.Group(
                gap="sm",
                mb="lg",
                children=[
                    dmc.ThemeIcon(
                        size="xl",
                        variant="light",
                        color="teal",
                        radius="md",
                        children=DashIconify(icon="solar:shield-network-bold-duotone", width=28),
                    ),
                    dmc.Stack(
                        gap=0,
                        children=[
                            dmc.Text("Internal source mappings", fw=700, size="xl", c="#2B3674"),
                            dmc.Text(
                                "Bulutistan's own resources — same source-mapping logic as Customer aliases.",
                                size="sm",
                                c="#A3AED0",
                            ),
                        ],
                    ),
                ],
            ),
            summary_strip(alias),
            html.Div(id="internal-alias-feedback", style={"marginBottom": "12px"}),
            banner,
            editor_paper,
            dcc.Store(id="internal-alias-editor-state", data=editor_state),
            dcc.Store(id="internal-alias-editor-open-sections", data=open_sections),
        ],
    )
