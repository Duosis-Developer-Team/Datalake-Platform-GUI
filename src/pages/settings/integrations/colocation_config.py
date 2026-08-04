"""Integrations — Colocation Configuration (gui_colocation_role_rule).

Hangi Loki rack rolünün sellable colocation U hesabına gireceğini operatör
buradan ayarlar. Ayar GLOBAL'dir; DC bazlı istisna kapsam dışı (spec §3).
"""

from __future__ import annotations

from dash import dcc, html
import dash_mantine_components as dmc
from dash_iconify import DashIconify

from src.services import api_client as api
from src.utils.colocation_config_ui import (
    build_role_table,
    merge_rules_with_catalog,
    preview_sellable_free_u,
    render_sellable_total,
)
from src.utils.ui_tokens import card_style, section_header, settings_page_shell

# Roles that also mean "allocated to a colocation customer"
# (shared.colocation.allocation.COLOCATION_ROLE_IDS). Making one of these
# sellable double-counts the same U as both allocated and for sale, which is
# the bug fixed in commit 7cd4c9e2 -- so the save path warns first.
COLOCATION_ROLE_IDS = ("3", "4")


def _impact_card() -> dmc.Alert:
    return dmc.Alert(
        color="indigo",
        variant="light",
        icon=DashIconify(icon="solar:info-circle-bold-duotone", width=20),
        title="Bu ayar neyi değiştirir?",
        children=dmc.Stack(gap=4, children=[
            dmc.Text("• DC Colocation kartındaki Sellable Free U ve TL potansiyeli", size="sm"),
            dmc.Text("• CRM Sellable Potential panelindeki dc_hosting_u", size="sm"),
            dmc.Text(
                "Fiziksel Total / Used / Free U tile'ları ETKİLENMEZ — onlar "
                "kabinlerin fiziksel gerçeği, satılabilirlik değil.",
                size="sm", fw=600,
            ),
        ]),
        mb="md",
    )


def build_layout(search: str | None = None) -> html.Div:
    _ = search
    payload = api.get_colocation_role_rules() or {}
    coloc = api.get_colocation("*") or {}
    breakdown = (coloc.get("aggregate") or {}).get("role_breakdown") or []
    merged = merge_rules_with_catalog(
        payload.get("rules"), payload.get("catalog"), breakdown
    )
    degraded = bool(payload.get("degraded"))
    current = preview_sellable_free_u(merged, {})

    banner = dmc.Alert(
        "Ayar veritabanına ulaşılamıyor. Gösterilen kurallar yerleşik "
        "varsayılan, kaydedilmiş ayar değil — kaydetme kapalı.",
        color="red", variant="light", mb="md",
    ) if degraded else None

    return html.Div(settings_page_shell([
        dcc.Store(id="coloc-cfg-store", data={"merged": merged, "etag": payload.get("etag")}),
        section_header(
            "Colocation Configuration",
            "Sellable colocation U hesabına hangi rack rolleri girsin? "
            "Ayar platform genelinde geçerlidir.",
            icon="solar:server-square-cloud-bold-duotone",
        ),
        banner if banner else html.Div(),
        _impact_card(),
        dmc.Paper(
            children=[
                html.Div(id="coloc-cfg-table", children=build_role_table(merged)),
                dmc.Divider(mt="lg", mb="md"),
                dmc.Group(justify="space-between", align="center", children=[
                    dmc.Stack(gap=2, children=[
                        dmc.Text(
                            "SELLABLE FREE U", size="xs", fw=700, c="dimmed",
                            style={"letterSpacing": "0.06em"},
                        ),
                        html.Div(id="coloc-cfg-preview", children=render_sellable_total(current, current)),
                    ]),
                    dmc.Button(
                        "Kaydet",
                        id="coloc-cfg-save",
                        disabled=degraded,
                        variant="gradient",
                        gradient={"from": "indigo", "to": "violet", "deg": 105},
                        leftSection=DashIconify(icon="solar:diskette-bold-duotone", width=18),
                    ),
                ]),
                html.Div(id="coloc-cfg-msg", style={"marginTop": "8px"}),
            ],
            **card_style(),
        ),
        dmc.Modal(
            id="coloc-cfg-confirm",
            title="Emin misiniz?",
            opened=False,
            children=[
                dmc.Text(id="coloc-cfg-confirm-body", size="sm"),
                dmc.Group(justify="flex-end", gap="sm", mt="md", children=[
                    dmc.Button("Vazgeç", id="coloc-cfg-confirm-cancel",
                               variant="subtle", color="gray"),
                    dmc.Button("Yine de kaydet", id="coloc-cfg-confirm-ok", color="red"),
                ]),
            ],
        ),
    ]))
