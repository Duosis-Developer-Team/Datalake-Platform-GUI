"""Platform — Compute / Storage coupling per virtualization environment.

One question per environment: when a family runs out of CPU/RAM, is its free
disk still sellable?

* ``merged``   — no. Storage joins the compute ``min()`` and is capped by the
  compute bottleneck (hyperconverged semantics: the disk lives in the same
  nodes, so with no node left the disk is dead weight).
* ``separate`` — yes. Storage is sized from its own pool and is never capped by
  CPU/RAM (classic VMware + external SAN, IBM Power semantics).
* ``auto``     — keep the built-in pipeline behaviour (per-host
  ``host_storage_in_triple`` for host-based families, family ratio + storage cap
  otherwise). Every family ships as ``auto``, so this page changes nothing until
  an operator moves a card.

Backed by ``gui_family_storage_coupling`` (migration 037) through
``/api/v1/crm/storage-coupling``. ``dc_code='*'`` is the default row; per-DC rows
override it, and dropping a card back into "Inherits default" deletes the
override.
"""
from __future__ import annotations

from typing import Any

import dash_mantine_components as dmc
from dash import Input, Output, State, callback, dash_table, dcc, html, no_update
from dash_iconify import DashIconify

from src.services import api_client as api
from src.utils.ui_tokens import card_style, section_header, settings_page_shell

_BOARD_ID = "csc-board"
_STORE_ID = "csc-board-state"
_SCOPE_ID = "csc-scope"
_TABLE_ID = "csc-table"

_DEFAULT_SCOPE = "*"
_INHERIT = "inherit"

# Families seeded by migration 037 — used as the card list when the config DB is
# empty or unreachable so the board is never blank.
_FALLBACK_FAMILIES: tuple[str, ...] = (
    "virt_classic",
    "virt_hyperconverged",
    "virt_intel_hana",
    "virt_km",
    "virt_power",
    "virt_power_hana",
)

_FAMILY_LABELS: dict[str, str] = {
    "virt_classic": "Klasik Mimari (VMware)",
    "virt_hyperconverged": "Hyperconverged (Nutanix)",
    "virt_intel_hana": "SAP HANA — Intel",
    "virt_km": "Klasik Mimari (KM kümesi)",
    "virt_power": "IBM Power",
    "virt_power_hana": "SAP HANA — Power",
}

# (mode, title, subtitle, colour, icon)
_ZONE_DEFS: tuple[tuple[str, str, str, str, str], ...] = (
    (
        _INHERIT,
        "Inherits default",
        "No row for this DC — follows the '*' default. Saving drops any override.",
        "gray",
        "solar:link-round-angle-bold-duotone",
    ),
    (
        "auto",
        "Auto (built-in)",
        "Pipeline decides per family/host, exactly as it does today.",
        "indigo",
        "solar:magic-stick-3-bold-duotone",
    ),
    (
        "merged",
        "Merged pool",
        "Storage joins the compute min(); free disk stops being sellable once CPU/RAM runs out.",
        "teal",
        "solar:layers-minimalistic-bold-duotone",
    ),
    (
        "separate",
        "Separate pools",
        "Storage is sized from its own pool and is never capped by CPU/RAM.",
        "orange",
        "solar:sidebar-minimalistic-bold-duotone",
    ),
)

_ZONE_COLORS: dict[str, str] = {m: c for m, _t, _s, c, _i in _ZONE_DEFS}


# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------


def _load_rows() -> tuple[list[dict[str, Any]], str | None]:
    """Saved coupling rows plus an error string when the API is unreachable."""
    try:
        rows = api.get_storage_couplings() or []
    except Exception as exc:  # noqa: BLE001 — page must render without the API
        return [], str(exc)
    out: list[dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        out.append(
            {
                "family": str(r.get("family") or ""),
                "dc_code": str(r.get("dc_code") or "*"),
                "mode": str(r.get("mode") or "auto"),
                "notes": str(r.get("notes") or ""),
                "updated_by": str(r.get("updated_by") or ""),
                "updated_at": str(r.get("updated_at") or "")[:19].replace("T", " "),
            }
        )
    return out, None


def _families(rows: list[dict[str, Any]]) -> list[str]:
    known = {r["family"] for r in rows if r.get("family")}
    return sorted(known | set(_FALLBACK_FAMILIES))


def _scope_options(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    codes: set[str] = {r["dc_code"] for r in rows if r.get("dc_code") and r["dc_code"] != "*"}
    try:
        for loc in (api.get_hmdl_locations() or {}).get("items") or []:
            code = str(loc.get("dc_code") or "").strip().upper()
            if code:
                codes.add(code)
    except Exception:  # noqa: BLE001 — the DC list is a convenience, not a requirement
        pass
    options = [{"value": _DEFAULT_SCOPE, "label": "All datacenters (default)"}]
    options += [{"value": c, "label": c} for c in sorted(codes)]
    return options


def _mode_map(rows: list[dict[str, Any]], scope: str) -> dict[str, str]:
    """``family -> mode`` for one scope; ``inherit`` when no per-DC row exists."""
    explicit = {r["family"]: r["mode"] for r in rows if r.get("dc_code") == scope}
    fallback = _INHERIT if scope != _DEFAULT_SCOPE else "auto"
    return {fam: explicit.get(fam, fallback) for fam in _families(rows)}


def _default_map(rows: list[dict[str, Any]]) -> dict[str, str]:
    return {r["family"]: r["mode"] for r in rows if r.get("dc_code") == _DEFAULT_SCOPE}


# ---------------------------------------------------------------------------
# board
# ---------------------------------------------------------------------------


def _card(family: str, mode: str, inherited: str | None) -> html.Div:
    label = _FAMILY_LABELS.get(family, family)
    meta: list[Any] = [
        html.Span(family, className="csc-card-family"),
    ]
    if inherited:
        meta.append(
            dmc.Badge(
                f"default: {inherited}",
                size="xs",
                variant="light",
                color=_ZONE_COLORS.get(inherited, "gray"),
            )
        )
    return html.Div(
        draggable="true",
        tabIndex=0,
        className="csc-card",
        **{
            "data-coupling-card": "1",
            "data-family": family,
            "data-initial-mode": mode,
            "aria-label": f"{label} — {mode}. Use the arrow keys to move it between columns.",
        },
        children=[
            dmc.Group(
                justify="space-between",
                gap="xs",
                wrap="nowrap",
                children=[
                    dmc.Text(label, size="sm", fw=600, c="#2B3674"),
                    html.Span(className="csc-card-dirty-dot", title="unsaved"),
                ],
            ),
            dmc.Group(gap="xs", mt=4, children=meta),
        ],
    )


def _zone(mode: str, title: str, subtitle: str, color: str, icon: str, cards: list[html.Div]) -> dmc.Paper:
    return dmc.Paper(
        **card_style(),
        children=[
            dmc.Group(
                justify="space-between",
                align="flex-start",
                gap="xs",
                mb=4,
                children=[
                    dmc.Group(
                        gap="xs",
                        children=[
                            DashIconify(icon=icon, width=18),
                            dmc.Text(title, fw=700, size="sm", c="#2B3674"),
                        ],
                    ),
                    dmc.Badge(
                        html.Span(str(len(cards)), **{"data-zone-count": mode}),
                        color=color,
                        variant="light",
                        size="sm",
                    ),
                ],
            ),
            dmc.Text(subtitle, size="xs", c="dimmed", mb="xs", style={"minHeight": "48px"}),
            html.Div(
                className="csc-zone-body" + ("" if cards else " csc-zone-body--empty"),
                **{"data-coupling-zone-body": "1", "data-mode": mode},
                children=cards,
            ),
        ],
    )


def _board(rows: list[dict[str, Any]], scope: str) -> dmc.SimpleGrid:
    assignment = _mode_map(rows, scope)
    defaults = _default_map(rows)
    zones = [z for z in _ZONE_DEFS if z[0] != _INHERIT or scope != _DEFAULT_SCOPE]
    return dmc.SimpleGrid(
        cols={"base": 1, "md": 2, "lg": len(zones)},
        spacing="md",
        children=[
            _zone(
                mode,
                title,
                subtitle,
                color,
                icon,
                [
                    _card(fam, mode, defaults.get(fam) if scope != _DEFAULT_SCOPE else None)
                    for fam, m in sorted(assignment.items())
                    if m == mode
                ],
            )
            for mode, title, subtitle, color, icon in zones
        ],
    )


def _example_alert() -> dmc.Alert:
    return dmc.Alert(
        color="indigo",
        variant="light",
        title="What the three columns do to the numbers",
        children=dmc.Stack(
            gap=4,
            children=[
                dmc.Text(
                    "Example — an environment with 100 vCPU / 800 GB RAM / 40 TB free disk "
                    "and a 1 vCPU : 8 GB RAM : 100 GB storage ratio:",
                    size="sm",
                ),
                dmc.Text(
                    "• Merged pool → units = min(100, 100, 409) = 100 → sellable storage = "
                    "100 × 100 GB = 10 TB. The other 30 TB is not counted, because there is "
                    "no compute left to sell with it.",
                    size="sm",
                ),
                dmc.Text(
                    "• Separate pools → CPU/RAM still sell 100 units, and storage keeps its "
                    "own 40 TB.",
                    size="sm",
                ),
                dmc.Text(
                    "• Auto → whatever the pipeline does today for that family. Nothing on "
                    "this page changes a number until you move a card out of Auto and save.",
                    size="sm",
                ),
            ],
        ),
    )


def _table(rows: list[dict[str, Any]]) -> dash_table.DataTable:
    return dash_table.DataTable(
        id=_TABLE_ID,
        data=rows,
        columns=[
            {"name": "family", "id": "family"},
            {"name": "dc_code", "id": "dc_code"},
            {"name": "mode", "id": "mode"},
            {"name": "notes", "id": "notes"},
            {"name": "updated_by", "id": "updated_by"},
            {"name": "updated_at", "id": "updated_at"},
        ],
        page_size=20,
        filter_action="native",
        sort_action="native",
        sort_mode="multi",
        style_table={"overflowX": "auto"},
        style_cell={"fontSize": "12px", "padding": "6px 8px", "textAlign": "left"},
        style_header={
            "backgroundColor": "#F4F7FE",
            "color": "#2B3674",
            "fontWeight": "700",
            "border": "none",
        },
        style_data_conditional=[
            {"if": {"filter_query": '{mode} = "merged"'}, "color": "#0E9384"},
            {"if": {"filter_query": '{mode} = "separate"'}, "color": "#C4531C"},
        ],
    )


def build_layout(search: str | None = None) -> html.Div:
    rows, error = _load_rows()
    scope = _DEFAULT_SCOPE

    return html.Div(
        settings_page_shell(
            [
                section_header(
                    "Compute / Storage",
                    "Per virtualization environment: is storage sold from the same pool as "
                    "compute, or on its own? Drag an environment into a column and save.",
                    icon="solar:server-square-cloud-bold-duotone",
                ),
                dmc.Alert(
                    f"Coupling rules could not be loaded: {error}",
                    title="API unavailable — showing defaults",
                    color="red",
                    variant="light",
                    mb="md",
                )
                if error
                else None,
                _example_alert(),
                dcc.Store(id=_STORE_ID, data=_mode_map(rows, scope)),
                dmc.Paper(
                    **card_style(),
                    mt="md",
                    mb="md",
                    children=[
                        dmc.Group(
                            justify="space-between",
                            align="flex-end",
                            children=[
                                dmc.Select(
                                    id=_SCOPE_ID,
                                    label="Scope",
                                    description="'*' is the default for every DC; pick a DC to override it there only.",
                                    data=_scope_options(rows),
                                    value=scope,
                                    size="xs",
                                    style={"minWidth": "280px"},
                                    allowDeselect=False,
                                ),
                                dmc.Group(
                                    gap="xs",
                                    children=[
                                        dmc.Button(
                                            "Reset",
                                            id="csc-reset",
                                            size="xs",
                                            variant="subtle",
                                            color="gray",
                                        ),
                                        dmc.Button("Save changes", id="csc-save", size="xs"),
                                    ],
                                ),
                            ],
                        ),
                        html.Div(id="csc-msg", style={"marginTop": "8px"}),
                    ],
                ),
                html.Div(id=_BOARD_ID, children=_board(rows, scope)),
                dmc.Text(
                    "Drag a card, or focus one with Tab and move it with ← / →. "
                    "A card with a blue edge has an unsaved change.",
                    size="xs",
                    c="dimmed",
                    mt="xs",
                    mb="md",
                ),
                dmc.Paper(
                    **card_style(),
                    children=[
                        dmc.Title("Saved rules", order=5, mb="xs"),
                        dmc.Text(
                            "Every stored row across all scopes. Rows with dc_code='*' are the "
                            "defaults; a DC row beats the default for that DC only.",
                            size="xs",
                            c="dimmed",
                            mb="sm",
                        ),
                        _table(rows),
                    ],
                ),
            ]
        )
    )


# ---------------------------------------------------------------------------
# callbacks
# ---------------------------------------------------------------------------


def _current_username() -> str:
    try:
        from flask import g, has_request_context

        if has_request_context():
            user = getattr(g, "auth_user", None) or {}
            name = str(user.get("username") or "").strip()
            if name:
                return name
    except Exception:  # noqa: BLE001 — audit label only
        pass
    return "settings-ui"


def _rebuild(scope: str) -> tuple[Any, dict[str, str], list[dict[str, Any]]]:
    rows, _error = _load_rows()
    return _board(rows, scope), _mode_map(rows, scope), rows


@callback(
    Output(_BOARD_ID, "children"),
    Output(_STORE_ID, "data"),
    Input(_SCOPE_ID, "value"),
    prevent_initial_call=True,
)
def _switch_scope(scope):
    board, state, _rows = _rebuild(str(scope or _DEFAULT_SCOPE))
    return board, state


@callback(
    Output(_BOARD_ID, "children", allow_duplicate=True),
    Output(_STORE_ID, "data", allow_duplicate=True),
    Output(_TABLE_ID, "data", allow_duplicate=True),
    Output("csc-msg", "children", allow_duplicate=True),
    Input("csc-reset", "n_clicks"),
    State(_SCOPE_ID, "value"),
    prevent_initial_call=True,
)
def _reset(_n, scope):
    board, state, rows = _rebuild(str(scope or _DEFAULT_SCOPE))
    return board, state, rows, dmc.Alert("Board reloaded from the database.", color="gray", variant="light")


@callback(
    Output("csc-msg", "children"),
    Output(_BOARD_ID, "children", allow_duplicate=True),
    Output(_STORE_ID, "data", allow_duplicate=True),
    Output(_TABLE_ID, "data", allow_duplicate=True),
    Input("csc-save", "n_clicks"),
    State(_STORE_ID, "data"),
    State(_SCOPE_ID, "value"),
    prevent_initial_call=True,
)
def _save(_n, state, scope):
    scope = str(scope or _DEFAULT_SCOPE)
    assignment = {str(k): str(v) for k, v in (state or {}).items()}
    if not assignment:
        return dmc.Alert("Nothing to save.", color="yellow", variant="light"), no_update, no_update, no_update

    rows, error = _load_rows()
    if error:
        return (
            dmc.Alert(error, title="Could not read the current rules", color="red", variant="light"),
            no_update,
            no_update,
            no_update,
        )

    current = _mode_map(rows, scope)
    upserts = [
        {"family": fam, "dc_code": scope, "mode": mode}
        for fam, mode in sorted(assignment.items())
        if mode != _INHERIT and current.get(fam) != mode
    ]
    deletes = [
        fam
        for fam, mode in sorted(assignment.items())
        if mode == _INHERIT and current.get(fam) not in (None, _INHERIT)
    ]
    if not upserts and not deletes:
        return dmc.Alert("No changes to save.", color="gray", variant="light"), no_update, no_update, no_update

    try:
        if upserts:
            api.put_storage_couplings(upserts, updated_by=_current_username())
        for fam in deletes:
            api.delete_storage_coupling(fam, scope)
    except Exception as exc:  # noqa: BLE001 — surface the API error in the UI
        return (
            dmc.Alert(str(exc), title="Save failed", color="red", variant="light"),
            no_update,
            no_update,
            no_update,
        )

    board, new_state, new_rows = _rebuild(scope)
    changed = ", ".join(f"{r['family']}→{r['mode']}" for r in upserts)
    dropped = ", ".join(f"{f}→inherit" for f in deletes)
    detail = " · ".join(p for p in (changed, dropped) if p)
    return (
        dmc.Alert(
            f"Saved for scope '{scope}': {detail}. Sellable numbers refresh on the next dashboard load.",
            title="Saved",
            color="green",
            variant="light",
        ),
        board,
        new_state,
        new_rows,
    )
