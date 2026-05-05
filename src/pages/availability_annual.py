"""Annual Availability report: single DC + calendar year (AuraNotify + product catalog)."""

from __future__ import annotations

from datetime import datetime, timezone

from dash import html, callback, Input, Output
import dash_mantine_components as dmc

from src.components.dc_availability_panel import build_dc_availability_panel
from src.services import api_client as api
from src.utils.dc_display import format_dc_display_name
from src.utils.time_range import MIN_REPORT_YEAR, calendar_year_range, default_time_range


def build_availability_annual_layout(visible_sections: set[str] | None = None) -> html.Div:
    """Shell with year + DC filters and body updated via callback."""

    def _sec(code: str) -> bool:
        if visible_sections is None:
            return True
        return code in visible_sections

    if not _sec("sec:availability_annual:report"):
        return html.Div(
            dmc.Alert(
                "You do not have permission to view this report.",
                color="red",
                variant="light",
            ),
            style={"padding": "24px"},
        )

    tr_list = default_time_range()
    datacenters = api.get_all_datacenters_summary(tr_list)
    current_year = datetime.now(timezone.utc).year
    year_options = [{"value": y, "label": str(y)} for y in range(MIN_REPORT_YEAR, current_year + 1)]
    dc_options: list[dict] = []
    default_dc_id: str | None = None
    for dc in datacenters:
        cid = dc.get("id")
        if cid is None:
            continue
        sid = str(cid)
        label = format_dc_display_name(dc.get("name"), dc.get("description")) or str(dc.get("name") or sid)
        dc_options.append({"value": sid, "label": label})
        if default_dc_id is None:
            default_dc_id = sid

    if not dc_options:
        return html.Div(
            dmc.Alert("No data centers available for this environment.", color="gray", variant="light"),
            style={"padding": "24px 32px"},
        )

    header = html.Div(
        style={"padding": "0 32px 16px"},
        children=[
            dmc.Stack(
                gap="sm",
                children=[
                    dmc.Text("Annual Availability", fw=700, size="xl", c="#2B3674"),
                    dmc.Group(
                        gap="md",
                        align="flex-end",
                        wrap="wrap",
                        children=[
                            dmc.Select(
                                label="Year",
                                id="availability-annual-year",
                                data=year_options,
                                value=current_year,
                                w=160,
                                searchable=False,
                                clearable=False,
                            ),
                            dmc.Select(
                                label="Data center",
                                id="availability-annual-dc",
                                data=dc_options,
                                value=default_dc_id,
                                searchable=True,
                                clearable=False,
                                nothingFoundMessage="No DCs",
                                style={"flex": "1 1 320px", "minWidth": "280px"},
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )

    body = html.Div(id="availability-annual-body")
    return html.Div([header, body])


@callback(
    Output("availability-annual-body", "children"),
    Input("availability-annual-year", "value"),
    Input("availability-annual-dc", "value"),
)
def _render_availability_annual_body(year, dc_id):
    current_year = datetime.now(timezone.utc).year
    try:
        y = int(year) if year is not None else current_year
    except (TypeError, ValueError):
        y = current_year

    tr = calendar_year_range(y)
    sel = str(dc_id).strip() if dc_id not in (None, "") else ""
    if not sel:
        return html.Div(
            style={"padding": "0 32px"},
            children=[
                dmc.Alert(
                    "Select a data center.",
                    color="gray",
                    variant="light",
                ),
            ],
        )

    tr_list = default_time_range()
    all_dcs = api.get_all_datacenters_summary(tr_list)
    row_by_id = {str(r.get("id")): r for r in all_dcs if r.get("id") is not None}
    row = row_by_id.get(sel)
    if not row:
        return html.Div(
            style={"padding": "0 32px"},
            children=[dmc.Alert("No matching data center found.", color="orange", variant="light")],
        )

    items_map = api.get_dc_availability_sla_items_for_dcs([row], tr)

    intro = dmc.Text(
        f"Year {y} — Report period (UTC): {tr['start']} — {tr['end']}",
        size="sm",
        c="dimmed",
        mb="md",
    )

    sid = str(row.get("id"))
    display = format_dc_display_name(row.get("name"), row.get("description")) or str(row.get("name") or sid)
    item = items_map.get(sid)

    return html.Div(
        style={"padding": "0 32px 32px"},
        children=[
            intro,
            html.Div(
                className="nexus-card",
                style={"padding": "8px 0 24px"},
                children=[build_dc_availability_panel(item, display)],
            ),
        ],
    )
