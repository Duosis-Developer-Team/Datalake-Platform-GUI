"""Annual Availability report: multi-DC + calendar year (AuraNotify + product catalog)."""

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
    default_dc_values: list[str] = []
    for dc in datacenters:
        cid = dc.get("id")
        if cid is None:
            continue
        sid = str(cid)
        label = format_dc_display_name(dc.get("name"), dc.get("description")) or str(dc.get("name") or sid)
        dc_options.append({"value": sid, "label": label})
        default_dc_values.append(sid)

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
                                w=140,
                                searchable=False,
                            ),
                            dmc.MultiSelect(
                                label="Data centers",
                                id="availability-annual-dcs",
                                data=dc_options,
                                value=default_dc_values,
                                searchable=True,
                                clearable=True,
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
    Input("availability-annual-dcs", "value"),
)
def _render_availability_annual_body(year, dc_ids):
    current_year = datetime.now(timezone.utc).year
    try:
        y = int(year) if year is not None else current_year
    except (TypeError, ValueError):
        y = current_year

    tr = calendar_year_range(y)
    sel = [str(x) for x in (dc_ids or []) if x]
    if not sel:
        return html.Div(
            style={"padding": "0 32px"},
            children=[
                dmc.Alert(
                    "Select at least one data center.",
                    color="gray",
                    variant="light",
                ),
            ],
        )

    tr_list = default_time_range()
    all_dcs = api.get_all_datacenters_summary(tr_list)
    row_by_id = {str(r.get("id")): r for r in all_dcs if r.get("id") is not None}
    ordered = [row_by_id[i] for i in sel if i in row_by_id]
    if not ordered:
        return html.Div(
            style={"padding": "0 32px"},
            children=[dmc.Alert("No matching data centers found.", color="orange", variant="light")],
        )

    items_map = api.get_dc_availability_sla_items_for_dcs(ordered, tr)

    intro = dmc.Text(
        f"Year {y} — Report period (UTC): {tr['start']} — {tr['end']}",
        size="sm",
        c="dimmed",
        mb="md",
    )

    sections: list = [intro]
    for row in ordered:
        sid = str(row.get("id"))
        display = format_dc_display_name(row.get("name"), row.get("description")) or str(
            row.get("name") or sid
        )
        item = items_map.get(sid)
        sections.append(
            html.Div(
                className="nexus-card",
                style={"padding": "8px 0 24px"},
                children=[
                    build_dc_availability_panel(item, display),
                ],
            )
        )

    return html.Div(style={"padding": "0 32px 32px"}, children=sections)
