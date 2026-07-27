"""Eşleşmeyen Veriler (Unmapped data customer): VMs and NetBackup policies.

A synthetic, resource-focused customer page: every VM (Sanallaştırma tab) and
backup policy (Backup tab) matching no customer at all, split into an
actionable *alias_gap* worklist, true *orphan* resources, and *ambiguous* ones
matching more than one customer (no action offered). Deliberately lightweight
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
_PLATFORM_LABEL = {"vmware": "VMware", "nutanix": "Nutanix", "netbackup": "NetBackup"}

ACTION_LABEL = "Alias ekle"
# Canonical route from src/pages/settings/shell.py:85 (ADMIN_PREFIX =
# "/administration"). The hint previously pointed at
# /settings/integrations/crm/internal-aliases, which is both the wrong page
# and the wrong prefix.
CUSTOMER_ALIASES_HREF = "/administration/integrations/crm/aliases"

BODY_ID = "unmapped-body"
TOAST_ID = "unmapped-toast"
STORE_ID = "unmapped-store"


def table_id(kind: str) -> dict[str, str]:
    """Pattern-matching id so one callback serves every source tab."""
    return {"type": "unmapped-table", "kind": kind}


def find_payload_row(store: dict, row_key: str | None) -> dict | None:
    """Resolve a clicked table row back to its full payload row.

    Matched on row_key rather than viewport index: active_cell reports the
    index within the current page of a sorted/filtered view, which does not
    address the payload.
    """
    if not row_key:
        return None
    for r in (store or {}).get("rows") or []:
        if f"{r.get('kind') or 'vm'}::{r.get('name') or ''}" == row_key:
            return r
    return None


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
        kind = r.get("kind") or "vm"
        actionable = bool(r.get("reason") == "alias_gap" and r.get("guessed_owner_id")
                          and r.get("suggested_alias"))
        reason_key = r.get("reason") or ""
        if reason_key == "ambiguous":
            reason = f"Belirsiz ({int(r.get('candidate_count') or 0)} aday)"
        else:
            reason = _REASON_LABEL.get(reason_key, reason_key)
        out.append({
            # active_cell reports a viewport row index, which moves as soon as
            # the operator sorts or filters. The click handler resolves the row
            # through this key instead.
            "row_key": f"{kind}::{r.get('name') or ''}",
            "guessed_owner": r.get("guessed_owner") or "—",
            "name": r.get("name") or "",
            "platform": _PLATFORM_LABEL.get(r.get("platform"), r.get("platform") or ""),
            "reason": reason,
            "action": ACTION_LABEL if actionable else "",
        })
    return out


def _header() -> dmc.Group:
    return dmc.Group(justify="space-between", align="center", mb="xs", children=[
        dmc.Group(gap="sm", children=[
            dmc.ThemeIcon(DashIconify(icon="solar:link-broken-bold-duotone", width=26),
                          size=46, radius="md", variant="light", color="gray"),
            dmc.Stack(gap=0, children=[
                dmc.Title(ACCOUNT_NAME, order=2),
                dmc.Text("Hiçbir müşteriye eşleşmeyen kaynaklar: sanal makineler ve "
                         "yedekleme politikaları.",
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


def _hint() -> dmc.Alert:
    return dmc.Alert(
        color="blue", variant="light", mb="md",
        title="Alias eksik olanlar bir iş listesidir",
        children=[
            "‘Alias eksik’ satırlar aslında gerçek bir müşterinin makineleridir; adı "
            "eşleşmediği için sahipsiz görünürler. ‘İŞLEM’ sütunundaki ‘Alias ekle’ "
            "bağlantısı kuralı tek tıkla ekler; elle düzenlemek için ",
            dcc.Link("Ayarlar › CRM › Müşteri Alias", href=CUSTOMER_ALIASES_HREF),
            " ekranını kullanın.",
        ],
    )


def build_layout(tr: dict | None = None, visible_sections=None) -> html.Div:
    tr = tr or default_time_range()
    return html.Div(style={"padding": "8px 4px"}, children=[
        _header(),
        html.Div(id=TOAST_ID),
        html.Div(id=BODY_ID, children=build_body(tr)),
    ])


def build_body(tr: dict | None = None) -> list:
    """KPIs, hint and tables — re-rendered after a successful alias write."""
    tr = tr or default_time_range()
    try:
        data = api.get_unmapped_resources(tr)
    except Exception:
        data = {"rows": [], "total": 0, "alias_gap_count": 0, "orphan_count": 0,
                "ambiguous_count": 0}

    rows = data.get("rows") or []
    total = int(data.get("total") or 0)
    alias_gap = int(data.get("alias_gap_count") or 0)
    orphan = int(data.get("orphan_count") or 0)

    vm_rows = [r for r in rows if (r.get("kind") or "vm") == "vm"]
    backup_rows = [r for r in rows if r.get("kind") == "backup"]
    ambiguous = int(data.get("ambiguous_count") or 0)

    kpi_cards = [
        _kpi("Toplam eşleşmeyen", total, "solar:server-square-bold-duotone", "#4318FF"),
        _kpi("Alias eksik (düzeltilebilir)", alias_gap, "solar:pen-new-square-bold-duotone", "#FFB547"),
        _kpi("Sahipsiz", orphan, "solar:ghost-bold-duotone", "#A3AED0"),
    ]
    if ambiguous:
        # Only shown when it exists: a permanent zero card would read as a
        # state the operator has to clear.
        kpi_cards.append(
            _kpi("Belirsiz (elle seçim)", ambiguous, "solar:question-circle-bold-duotone", "#B26A00")
        )
    # KPIs stay source-agnostic on purpose; per-tab counts live on the tab
    # badges, so the page never shows two different readings of "total".
    kpis = dmc.SimpleGrid(cols={"base": 1, "sm": len(kpi_cards)}, spacing="md", mb="md",
                          children=kpi_cards)

    tabs = dmc.Tabs(value="virt", children=[
        dmc.TabsList([
            dmc.TabsTab("Sanallaştırma", value="virt",
                        rightSection=dmc.Badge(str(len(vm_rows)), size="xs",
                                               variant="light", color="indigo")),
            dmc.TabsTab("Backup", value="backup",
                        rightSection=dmc.Badge(str(len(backup_rows)), size="xs",
                                               variant="light", color="indigo")),
        ]),
        dmc.TabsPanel(value="virt", pt="md", children=_vm_table(vm_rows)),
        dmc.TabsPanel(value="backup", pt="md", children=_backup_table(backup_rows)),
    ])

    return [
        dcc.Store(id=STORE_ID, data={"rows": rows, "time_range": tr}),
        kpis,
        _hint(),
        tabs,
    ]


def _table_shell(rows: list[dict], *, kind: str, name_header: str,
                 source_header: str, hint: str) -> html.Div:
    """The card + DataTable both source tabs share.

    Only the two headers and the hint differ between them, so the styling
    lives here once; a second copy would drift the moment one is tweaked.
    """
    return html.Div(className="nexus-card", style={"padding": "20px"}, children=[
        html.Div(style={"height": "2px", "width": "32px", "borderRadius": "2px",
                        "marginBottom": "12px",
                        "background": "linear-gradient(90deg,#4318FF,#FFB547)"}),
        dmc.Text(hint, size="xs", c="#A3AED0", mb="sm"),
        dash_table.DataTable(
            id=table_id(kind),
            data=_table_rows(rows),
            columns=[
                {"name": "TAHMİNİ SAHİP", "id": "guessed_owner"},
                {"name": name_header, "id": "name"},
                {"name": source_header, "id": "platform"},
                {"name": "NEDEN", "id": "reason"},
                {"name": "İŞLEM", "id": "action"},
            ],
            hidden_columns=["row_key"],
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
                # The cell IS the button: DataTable cannot host a component, and
                # replacing the table with html.Table would cost the native
                # column filtering and sorting this page advertises above.
                {"if": {"column_id": "action", "filter_query": f"{{action}} = '{ACTION_LABEL}'"},
                 "color": "#4318FF", "fontWeight": "700", "cursor": "pointer",
                 "textDecoration": "underline"},
                {"if": {"filter_query": "{reason} = 'Alias eksik'"},
                 "backgroundColor": "rgba(255,181,71,0.07)"},
                {"if": {"filter_query": "{reason} = 'Alias eksik'", "column_id": "reason"},
                 "color": "#B26A00", "fontWeight": "700"},
                {"if": {"filter_query": "{reason} contains 'Belirsiz'", "column_id": "reason"},
                 "color": "#B26A00", "fontWeight": "700"},
                {"if": {"filter_query": "{reason} = 'Sahipsiz'", "column_id": "reason"},
                 "color": "#A3AED0", "fontWeight": "600"},
                {"if": {"state": "active"},
                 "backgroundColor": "rgba(67,24,255,0.06)", "border": "none"},
            ],
        ),
    ])


def _vm_table(rows: list[dict]) -> html.Div:
    if not rows:
        return dmc.Alert(color="teal", variant="light", title="Eşleşmeyen makine yok",
                         children="Seçili zaman aralığında hiçbir sahipsiz sanal makine bulunamadı.")
    return _table_shell(
        rows, kind="vm", name_header="MAKİNE ADI", source_header="PLATFORM",
        hint="Sütun başlıklarından filtreleyin, başlığa tıklayarak sıralayın. "
             "Amber satırlar alias eklenerek bir müşteriye bağlanabilir.",
    )


def _backup_table(rows: list[dict]) -> html.Div:
    if not rows:
        return dmc.Alert(color="teal", variant="light", title="Eşleşmeyen backup yok",
                         children="Seçili zaman aralığında sahipsiz bir yedekleme "
                                  "politikası bulunamadı.")
    return _table_shell(
        rows, kind="backup", name_header="POLICY ADI", source_header="KAYNAK",
        hint="Policy adları ‘müşteri-workload-ortam-tip’ standardına göre eşleştirilir. "
             "‘Belirsiz’ satırlarda aynı önek birden fazla müşteriye uyar; doğru "
             "müşteriyi Müşteri Alias ekranından seçin.",
    )
