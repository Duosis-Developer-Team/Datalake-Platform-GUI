"""
Settings — CRM product → service page mapping (YAML seed in DB + operator overrides).

Route: /settings/integrations/crm/service-mapping
"""
from __future__ import annotations

import dash
from dash import Input, Output, State, callback, ctx, dcc, html
import dash_mantine_components as dmc
from dash_iconify import DashIconify

from src.services import api_client as api


_BADGE_COLORS = {
    "override": "teal",
    "yaml": "gray",
    "unmatched": "orange",
}


def build_layout(search: str | None = None) -> html.Div:
    rows = api.get_crm_service_mappings()
    pages = api.get_crm_service_mapping_pages()
    page_options = [{"value": p.get("page_key", ""), "label": f"{p.get('page_key')} — {p.get('category_label', '')}"} for p in pages if p.get("page_key")]

    if not rows:
        body = dmc.Alert(
            color="yellow",
            title="No data",
            children="Run the webui-db migrations (001-004) and ensure discovery_crm_products is populated.",
        )
    else:
        unmatched_count = sum(1 for r in rows if str(r.get("source") or "") == "unmatched")
        table_rows = []
        for r in rows:
            pid = str(r.get("productid", ""))
            eff = str(r.get("category_code") or "")
            src = str(r.get("source", "") or "")
            badge_color = _BADGE_COLORS.get(src, "gray")
            badge_label = src.upper() if src else "-"
            table_rows.append(
                html.Tr(
                    [
                        html.Td(pid, style={"fontSize": "11px", "maxWidth": "120px", "wordBreak": "break-all"}),
                        html.Td((r.get("product_name") or "-")[:60]),
                        html.Td((r.get("product_number") or "-")[:24]),
                        html.Td(
                            eff or html.Span("—", style={"color": "#A3AED0"}),
                            style={"fontSize": "12px"},
                        ),
                        html.Td(
                            dmc.Badge(
                                badge_label,
                                color=badge_color,
                                variant="light" if src == "unmatched" else "filled",
                                size="sm",
                            )
                        ),
                        html.Td(
                            dmc.Select(
                                id={"type": "svcmap-page", "index": pid},
                                data=page_options,
                                value=eff or None,
                                size="xs",
                                searchable=True,
                                clearable=True,
                                placeholder="Select page_key…",
                                style={"minWidth": "260px"},
                            )
                        ),
                        html.Td(
                            dmc.TextInput(
                                id={"type": "svcmap-notes", "index": pid},
                                value="",
                                placeholder="notes (optional)",
                                size="xs",
                                style={"minWidth": "140px"},
                            )
                        ),
                        html.Td(
                            dmc.Group(
                                gap="xs",
                                wrap="nowrap",
                                children=[
                                    dmc.Button(
                                        "Save",
                                        id={"type": "svcmap-save", "index": pid},
                                        size="xs",
                                        color="indigo",
                                        variant="light",
                                    ),
                                    dmc.Button(
                                        "Reset",
                                        id={"type": "svcmap-reset", "index": pid},
                                        size="xs",
                                        color="gray",
                                        variant="subtle",
                                    ),
                                ],
                            )
                        ),
                    ]
                )
            )
        table = dmc.Table(
            striped=True,
            highlightOnHover=True,
            withTableBorder=True,
            children=[
                html.Thead(
                    html.Tr(
                        [
                            html.Th("Product ID"),
                            html.Th("Name"),
                            html.Th("Number"),
                            html.Th("Effective page_key"),
                            html.Th("Source"),
                            html.Th("Override"),
                            html.Th("Notes"),
                            html.Th(""),
                        ]
                    )
                ),
                html.Tbody(table_rows),
            ],
        )
        body = html.Div(style={"overflowX": "auto"}, children=[table])

    summary_alert = None
    if rows:
        if unmatched_count:
            summary_alert = dmc.Alert(
                color="orange",
                variant="light",
                title=f"{unmatched_count} unmatched CRM products",
                children=(
                    "Pick a page_key to map them to a WebUI panel (e.g. virt_hyperconverged_ram, "
                    "backup_zerto_storage). Leave them as UNMATCHED if they should not feed any panel yet."
                ),
                style={"marginBottom": "12px"},
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
                        color="indigo",
                        radius="md",
                        children=DashIconify(icon="solar:widget-4-bold-duotone", width=28),
                    ),
                    dmc.Stack(
                        gap=0,
                        children=[
                            dmc.Text("CRM service mapping", fw=700, size="xl", c="#2B3674"),
                            dmc.Text(
                                "Each CRM product maps to exactly one WebUI panel via page_key. "
                                "YAML seed produces the default mapping; Save writes a manual "
                                "override, Reset removes it. Products without a mapping are flagged "
                                "as UNMATCHED so operators can resolve them.",
                                size="sm",
                                c="#A3AED0",
                            ),
                        ],
                    ),
                ],
            ),
            summary_alert,
            dcc.Store(id="svcmap-dummy"),
            html.Div(id="svcmap-feedback", style={"marginBottom": "12px"}),
            body,
        ],
    )


@callback(
    Output("svcmap-feedback", "children"),
    Input({"type": "svcmap-save", "index": dash.ALL}, "n_clicks"),
    State({"type": "svcmap-page", "index": dash.ALL}, "value"),
    State({"type": "svcmap-notes", "index": dash.ALL}, "value"),
    State({"type": "svcmap-save", "index": dash.ALL}, "id"),
    prevent_initial_call=True,
)
def _on_svcmap_save(_n, page_vals, notes_vals, save_ids):
    if not ctx.triggered:
        return dash.no_update
    trig = ctx.triggered_id
    if not isinstance(trig, dict) or trig.get("type") != "svcmap-save":
        return dash.no_update
    idx = trig.get("index")
    if not idx:
        return dash.no_update
    id_list = [i.get("index") for i in (save_ids or []) if isinstance(i, dict)]
    try:
        pos = id_list.index(idx)
    except ValueError:
        return dmc.Alert(color="red", title="Error", children="Row not found.")
    page_key = (page_vals or [""])[pos] or ""
    notes = (notes_vals or [""])[pos] or None
    if not page_key:
        # Empty selection — treat as "leave unmatched": clear any existing override.
        api.delete_crm_service_mapping_override(str(idx))
        return dmc.Alert(
            color="orange",
            variant="light",
            title="Marked unmatched",
            children=f"Cleared mapping for {idx}.",
        )
    api.put_crm_service_mapping(str(idx), page_key=page_key, notes=notes)
    return dmc.Alert(color="green", variant="light", title="Saved", children=f"Updated {idx} → {page_key}")


@callback(
    Output("svcmap-feedback", "children", allow_duplicate=True),
    Input({"type": "svcmap-reset", "index": dash.ALL}, "n_clicks"),
    State({"type": "svcmap-reset", "index": dash.ALL}, "id"),
    prevent_initial_call=True,
)
def _on_svcmap_reset(_n, reset_ids):
    if not ctx.triggered:
        return dash.no_update
    trig = ctx.triggered_id
    if not isinstance(trig, dict) or trig.get("type") != "svcmap-reset":
        return dash.no_update
    idx = trig.get("index")
    if not idx:
        return dash.no_update
    api.delete_crm_service_mapping_override(str(idx))
    return dmc.Alert(color="green", variant="light", title="Reset", children=f"Cleared override for {idx}")
