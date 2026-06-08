"""Integrations — NetBox/Loki visualization exclusions (gui_netbox_viz_exclusion)."""

from __future__ import annotations

import dash
from dash import Input, Output, State, callback, ctx, html
import dash_mantine_components as dmc

from src.services import api_client as api


def _role_options() -> list[dict[str, str]]:
    roles = api.get_netbox_device_roles()
    return [{"value": r["role"], "label": r["role"]} for r in roles if r.get("role")]


def _exclusion_table(rows: list[dict], scope: str) -> html.Table:
    scoped = [r for r in rows if str(r.get("view_scope") or "").lower() == scope]
    body_rows = []
    for r in scoped:
        rid = int(r.get("id") or 0)
        body_rows.append(
            html.Tr(
                [
                    html.Td(str(r.get("dimension_value") or "")),
                    html.Td(str(r.get("notes") or "")),
                    html.Td(str(r.get("updated_by") or "")),
                    html.Td(
                        dmc.Button(
                            "Delete",
                            id={"type": "nbx-del", "rid": rid},
                            size="xs",
                            color="red",
                            variant="light",
                        )
                    ),
                ]
            )
        )
    return html.Table(
        className="table table-sm",
        style={"width": "100%", "borderCollapse": "collapse"},
        children=[
            html.Thead(
                html.Tr(
                    [
                        html.Th("Device role"),
                        html.Th("Notes"),
                        html.Th("Updated by"),
                        html.Th(""),
                    ]
                )
            ),
            html.Tbody(body_rows or [html.Tr([html.Td(colSpan=4, children="No exclusions yet")])]),
        ],
    )


def _scope_panel(scope: str, label: str, role_data: list[dict[str, str]], exclusions: list[dict]) -> dmc.TabsPanel:
    select_id = f"nbx-roles-{scope}"
    save_id = f"nbx-save-{scope}"
    notes_id = f"nbx-notes-{scope}"
    msg_id = f"nbx-msg-{scope}"
    table_id = f"nbx-table-{scope}"
    return dmc.TabsPanel(
        value=scope,
        children=[
            dmc.Text(
                f"Excluded roles are hidden from {label} physical inventory, network and storage views. "
                "Floor map rack devices are not affected.",
                size="sm",
                c="dimmed",
                mb="sm",
            ),
            dmc.Grid(
                gutter="sm",
                mb="md",
                children=[
                    dmc.GridCol(
                        span={"base": 12, "md": 8},
                        children=dmc.MultiSelect(
                            id=select_id,
                            label="Device roles to exclude",
                            data=role_data,
                            searchable=True,
                            clearable=True,
                            size="xs",
                        ),
                    ),
                    dmc.GridCol(
                        span={"base": 12, "md": 4},
                        children=dmc.TextInput(id=notes_id, label="Notes (optional)", size="xs"),
                    ),
                    dmc.GridCol(
                        span={"base": 12, "md": 12},
                        children=dmc.Button(f"Exclude selected roles ({label})", id=save_id, size="xs"),
                    ),
                ],
            ),
            html.Div(id=msg_id, style={"marginBottom": "8px"}),
            dmc.Title(f"Current exclusions — {label}", order=5, mb="sm"),
            html.Div(id=table_id, children=_exclusion_table(exclusions, scope)),
        ],
    )


def build_layout(search: str | None = None) -> html.Div:
    exclusions = api.get_netbox_viz_exclusions()
    role_data = _role_options()

    return html.Div(
        [
            dmc.Stack(
                gap="xs",
                mb="md",
                children=[
                    dmc.Title("NetBox / Loki visualization filters", order=3),
                    dmc.Text(
                        "Choose device roles to exclude from dashboards and aggregations. "
                        "Datacenter and customer scopes are independent.",
                        size="sm",
                        c="dimmed",
                    ),
                ],
            ),
            dmc.Paper(
                p="md",
                radius="md",
                withBorder=True,
                children=[
                    dmc.Tabs(
                        value="datacenter",
                        children=[
                            dmc.TabsList(
                                children=[
                                    dmc.TabsTab("Datacenter", value="datacenter"),
                                    dmc.TabsTab("Customer", value="customer"),
                                ]
                            ),
                            _scope_panel("datacenter", "datacenter", role_data, exclusions),
                            _scope_panel("customer", "customer", role_data, exclusions),
                        ],
                    ),
                    html.Div(id="nbx-del-msg", style={"marginTop": "8px"}),
                ],
            ),
        ]
    )


def _save_scope_exclusions(scope: str, roles: list[str] | None, notes: str | None):
    selected = [str(r).strip() for r in (roles or []) if str(r).strip()]
    if not selected:
        return dmc.Alert(color="yellow", title="Select at least one device role")
    try:
        for role in selected:
            api.put_netbox_viz_exclusion(
                view_scope=scope,
                dimension_value=role,
                notes=str(notes) if notes else None,
            )
        return dmc.Alert(
            color="green",
            title=f"Saved {len(selected)} exclusion(s) — refresh page to see table updates.",
        )
    except Exception as exc:  # noqa: BLE001
        return dmc.Alert(color="red", title="Save failed", children=str(exc))


@callback(
    Output("nbx-msg-datacenter", "children"),
    Input("nbx-save-datacenter", "n_clicks"),
    State("nbx-roles-datacenter", "value"),
    State("nbx-notes-datacenter", "value"),
    prevent_initial_call=True,
)
def _save_datacenter(_n, roles, notes):
    return _save_scope_exclusions("datacenter", roles, notes)


@callback(
    Output("nbx-msg-customer", "children"),
    Input("nbx-save-customer", "n_clicks"),
    State("nbx-roles-customer", "value"),
    State("nbx-notes-customer", "value"),
    prevent_initial_call=True,
)
def _save_customer(_n, roles, notes):
    return _save_scope_exclusions("customer", roles, notes)


@callback(
    Output("nbx-del-msg", "children"),
    Input({"type": "nbx-del", "rid": dash.ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def _del_exclusion(_clicks):
    trig = ctx.triggered_id
    if not isinstance(trig, dict) or trig.get("type") != "nbx-del":
        return dash.no_update
    rid = int(trig["rid"])
    try:
        api.delete_netbox_viz_exclusion(rid)
        return dmc.Alert(color="green", title="Deleted — refresh page.")
    except Exception as exc:  # noqa: BLE001
        return dmc.Alert(color="red", title="Delete failed", children=str(exc))
