"""Eşleşmeyen Veriler (Unmapped data customer) — Phase 1: VMs.

A synthetic, resource-focused customer page: every VM that matches no customer
at all, split into an actionable *alias_gap* worklist (a real customer's VM that
just needs a mapping rule) and true *orphan* resources. Deliberately lightweight
— it does NOT go through the heavy customer-view (no CRM / billing / SLA here).
"""
from __future__ import annotations

from dash import dash_table, dcc, html
import dash_mantine_components as dmc
from dash_iconify import DashIconify

from src.services import api_client as api
from src.utils.time_range import default_time_range

ACCOUNT_NAME = "Eşleşmeyen Veriler"

_REASON_LABEL = {"alias_gap": "Alias eksik", "orphan": "Sahipsiz"}
_PLATFORM_LABEL = {"vmware": "VMware", "nutanix": "Nutanix"}

_TABLE_ID = "unmapped-vm-table"


def _kpi(label: str, value, icon: str, accent: str) -> dmc.Paper:
    return dmc.Paper(
        p="md", radius="md", withBorder=True,
        style={
            "boxShadow": "0 4px 24px rgba(43,54,116,0.06)",
            "border": "1px solid rgba(163,174,208,0.18)",
            "borderLeft": f"4px solid {accent}",
            "background": "#ffffff",
        },
        children=dmc.Group(gap="sm", children=[
            dmc.ThemeIcon(
                DashIconify(icon=icon, width=22), size=42, radius="md", variant="light",
                style={"background": f"{accent}1A", "color": accent},
            ),
            dmc.Stack(gap=0, children=[
                dmc.Text(str(value), fw=800, size="xl", c="#2B3674",
                         style={"fontFamily": "DM Sans", "lineHeight": 1.1}),
                dmc.Text(label, size="xs", c="#A3AED0"),
            ]),
        ]),
    )


def _table_rows(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for r in rows:
        out.append({
            "guessed_owner": r.get("guessed_owner") or "—",
            "name": r.get("name") or "",
            "platform": _PLATFORM_LABEL.get(r.get("platform"), r.get("platform") or ""),
            "reason": _REASON_LABEL.get(r.get("reason"), r.get("reason") or ""),
        })
    return out


def build_layout(tr: dict | None = None, visible_sections=None) -> html.Div:
    tr = tr or default_time_range()
    try:
        data = api.get_unmapped_resources(tr)
    except Exception:
        data = {"rows": [], "total": 0, "alias_gap_count": 0, "orphan_count": 0}

    rows = data.get("rows") or []
    total = int(data.get("total") or 0)
    alias_gap = int(data.get("alias_gap_count") or 0)
    orphan = int(data.get("orphan_count") or 0)

    header = dmc.Group(justify="space-between", align="center", mb="xs", children=[
        dmc.Group(gap="sm", children=[
            dmc.ThemeIcon(DashIconify(icon="solar:link-broken-bold-duotone", width=26),
                          size=46, radius="md", variant="light", color="gray"),
            dmc.Stack(gap=0, children=[
                dmc.Title(ACCOUNT_NAME, order=2),
                dmc.Text("Hiçbir müşteriye eşleşmeyen kaynaklar (Faz 1: sanal makineler).",
                         size="sm", c="dimmed"),
            ]),
        ]),
        # "light" not "subtle": subtle paints no background until hover, so on a
        # fresh page load the only way back read as blank space.
        dcc.Link(
            dmc.Button(
                "Müşterilere dön",
                variant="light",
                size="sm",
                radius="md",
                leftSection=DashIconify(icon="tabler:arrow-left", width=16),
            ),
            href="/customers",
            style={"textDecoration": "none"},
        ),
    ])

    kpis = dmc.SimpleGrid(cols={"base": 1, "sm": 3}, spacing="md", mb="md", children=[
        _kpi("Toplam eşleşmeyen", total, "solar:server-square-bold-duotone", "#4318FF"),
        _kpi("Alias eksik (düzeltilebilir)", alias_gap, "solar:pen-new-square-bold-duotone", "#FFB547"),
        _kpi("Sahipsiz", orphan, "solar:ghost-bold-duotone", "#A3AED0"),
    ])

    hint = dmc.Alert(
        color="blue", variant="light", mb="md",
        title="Alias eksik olanlar bir iş listesidir",
        children=[
            "‘Alias eksik’ satırlar aslında gerçek bir müşterinin makineleridir; adı "
            "eşleşmediği için sahipsiz görünürler. ‘Tahmini sahip’ sütunundaki müşteri için ",
            dcc.Link("Ayarlar › CRM › İç Alias", href="/settings/integrations/crm/internal-aliases"),
            " ekranından bir eşleştirme kuralı eklendiğinde makine o müşteriye bağlanır.",
        ],
    )

    tabs = dmc.Tabs(value="virt", children=[
        dmc.TabsList([
            dmc.TabsTab("Sanallaştırma", value="virt"),
        ]),
        dmc.TabsPanel(value="virt", pt="md", children=_vm_table(rows)),
    ])

    return html.Div(style={"padding": "8px 4px"}, children=[header, kpis, hint, tabs])


def _vm_table(rows: list[dict]) -> html.Div:
    if not rows:
        return dmc.Alert(color="teal", variant="light", title="Eşleşmeyen makine yok",
                         children="Seçili zaman aralığında hiçbir sahipsiz sanal makine bulunamadı.")
    return html.Div(className="nexus-card", style={"padding": "20px"}, children=[
        html.Div(style={"height": "2px", "width": "32px", "borderRadius": "2px",
                        "marginBottom": "12px",
                        "background": "linear-gradient(90deg,#4318FF,#FFB547)"}),
        dmc.Text("Sütun başlıklarından filtreleyin, başlığa tıklayarak sıralayın. "
                 "Amber satırlar alias eklenerek bir müşteriye bağlanabilir.",
                 size="xs", c="#A3AED0", mb="sm"),
        dash_table.DataTable(
            id=_TABLE_ID,
            data=_table_rows(rows),
            columns=[
                {"name": "TAHMİNİ SAHİP", "id": "guessed_owner"},
                {"name": "MAKİNE ADI", "id": "name"},
                {"name": "PLATFORM", "id": "platform"},
                {"name": "NEDEN", "id": "reason"},
            ],
            page_size=25,
            filter_action="native",
            sort_action="native",
            sort_mode="multi",
            style_as_list_view=True,
            style_table={"overflowX": "auto"},
            style_cell={"fontSize": "12.5px", "padding": "10px 12px", "textAlign": "left",
                        "fontFamily": "DM Sans, Inter, system-ui, sans-serif",
                        "color": "#2B3674", "border": "none",
                        "borderBottom": "1px solid #eef1f4"},
            style_header={"backgroundColor": "#F4F7FE", "color": "#707EAE",
                          "fontWeight": "700", "fontSize": "10.5px",
                          "textTransform": "uppercase", "letterSpacing": "0.04em",
                          "border": "none", "padding": "10px 12px"},
            style_cell_conditional=[
                {"if": {"column_id": "name"}, "fontWeight": "600"},
                {"if": {"column_id": "guessed_owner"}, "color": "#707EAE"},
            ],
            style_data_conditional=[
                {"if": {"filter_query": "{reason} = 'Alias eksik'"},
                 "backgroundColor": "rgba(255,181,71,0.07)"},
                {"if": {"filter_query": "{reason} = 'Alias eksik'", "column_id": "reason"},
                 "color": "#B26A00", "fontWeight": "700"},
                {"if": {"filter_query": "{reason} = 'Sahipsiz'", "column_id": "reason"},
                 "color": "#A3AED0", "fontWeight": "600"},
                {"if": {"state": "active"},
                 "backgroundColor": "rgba(67,24,255,0.06)", "border": "none"},
            ],
        ),
    ])
