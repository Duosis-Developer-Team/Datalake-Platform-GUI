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

Backed by ``gui_family_storage_coupling`` (migrations 037 + 038) through
``/api/v1/crm/storage-coupling``. ``dc_code='*'`` is the default row; per-DC rows
override it, and dropping a card back into "Inherits default" deletes the
override.

Two levels of granularity:

* **Environment** (default) — one card per family, matching how the pipeline
  groups panels.
* **Cluster detail** (switch) — one card per cluster of a host-based family, for
  the selected DC. The built-in ``auto`` rule already decides per host, so this
  level exists for the day a cluster stops agreeing with its family. Measured
  2026-08-02: all 36 clusters agree, so every cluster starts on "inherit".
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
_DETAIL_ID = "csc-detail"

# Board card keys. Family cards keep the bare family name so the saved state of
# the default view is unchanged; cluster cards carry their scope in the key.
_CLUSTER_KEY_PREFIX = "cluster:"

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
    "backup_veeam_replication_classic",
    "backup_zerto_replication_classic",
    "backup_veeam_replication_hyperconverged",
    "backup_zerto_replication_hyperconverged",
)

_FAMILY_LABELS: dict[str, str] = {
    "virt_classic": "Klasik Mimari (VMware)",
    "virt_hyperconverged": "Hyperconverged (Nutanix)",
    "virt_intel_hana": "SAP HANA — Intel",
    "virt_km": "Klasik Mimari (KM kümesi)",
    "virt_power": "IBM Power",
    "virt_power_hana": "SAP HANA — Power",
    "backup_veeam_replication_classic": "Veeam Replication — Classic",
    "backup_zerto_replication_classic": "Zerto Replication — Classic",
    "backup_veeam_replication_hyperconverged": "Veeam Replication — HC",
    "backup_zerto_replication_hyperconverged": "Zerto Replication — HC",
}

# Families that both compute sellable host-by-host AND group their hosts into
# clusters, mapped to the cluster-list API that feeds the detail board. A cluster
# rule only bites where both hold: an aggregated family has no host row to attach
# it to, and virt_power -- host-based since /compute/power/hosts -- has no
# clusters, because an IBM frame stands alone.
# Replication Classic/HC borrow the same cluster lists as their virt host SoT.
_CLUSTER_SOURCES: dict[str, str] = {
    "virt_classic": "classic",
    "virt_hyperconverged": "hyperconverged",
    "backup_veeam_replication_classic": "classic",
    "backup_zerto_replication_classic": "classic",
    "backup_veeam_replication_hyperconverged": "hyperconverged",
    "backup_zerto_replication_hyperconverged": "hyperconverged",
}

# Overlaps the operator has to know about before setting a mode, shown on the
# card itself rather than buried in the notes column.
_FAMILY_WARNINGS: dict[str, str] = {
    "virt_km": "subset of Klasik Mimari — keep both consistent",
    "virt_power": "IBM storage is on shared arrays — separate in practice",
    "virt_power_hana": "shares IBM Power hardware with virt_power",
    "backup_veeam_replication_classic": (
        "host SoT from virt_classic; own ratios; storage separate by default"
    ),
    "backup_zerto_replication_classic": (
        "host SoT from virt_classic; own ratios; storage separate by default"
    ),
    "backup_veeam_replication_hyperconverged": (
        "host SoT from virt_hyperconverged; own ratios; storage separate by default"
    ),
    "backup_zerto_replication_hyperconverged": (
        "host SoT from virt_hyperconverged; own ratios; storage separate by default"
    ),
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

# The inherit zone means something one level down on the cluster board.
_INHERIT_SUBTITLE_CLUSTER = (
    "No row for this cluster — follows its environment. Saving drops any override."
)


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
                # Pre-038 rows have neither field and are family-scoped.
                "scope_kind": str(r.get("scope_kind") or "family"),
                "scope_key": str(r.get("scope_key") or ""),
                "mode": str(r.get("mode") or "auto"),
                "notes": str(r.get("notes") or ""),
                "updated_by": str(r.get("updated_by") or ""),
                "updated_at": str(r.get("updated_at") or "")[:19].replace("T", " "),
            }
        )
    return out, None


def _family_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if r.get("scope_kind", "family") == "family"]


def _families(rows: list[dict[str, Any]]) -> list[str]:
    known = {r["family"] for r in _family_rows(rows) if r.get("family")}
    return sorted(known | set(_FALLBACK_FAMILIES))


def _clusters_for(dc_code: str) -> list[tuple[str, str]]:
    """``(family, cluster)`` pairs of the host-based families in one DC.

    Returns an empty list for the ``'*'`` scope: cluster names are DC-local, so
    a global cluster rule would apply to whichever DC happens to reuse the name.
    """
    if not dc_code or dc_code == _DEFAULT_SCOPE:
        return []
    pairs: list[tuple[str, str]] = []
    for family, kind in _CLUSTER_SOURCES.items():
        try:
            if kind == "classic":
                names = api.get_classic_cluster_list(dc_code, None) or []
            else:
                names = api.get_hyperconv_cluster_list(dc_code, None) or []
        except Exception:  # noqa: BLE001 — detail view degrades to "no clusters"
            continue
        for name in names:
            text = str(name or "").strip()
            if text:
                pairs.append((family, text))
    return sorted(set(pairs))


def _cluster_key(family: str, cluster: str) -> str:
    return f"{_CLUSTER_KEY_PREFIX}{family}:{cluster}"


def _split_cluster_key(key: str) -> tuple[str, str] | None:
    """``cluster:<family>:<cluster name>`` back into its parts.

    Split from the left exactly twice so a cluster name containing a colon
    survives the round trip.
    """
    if not key.startswith(_CLUSTER_KEY_PREFIX):
        return None
    _, _, rest = key.partition(_CLUSTER_KEY_PREFIX)
    family, sep, cluster = rest.partition(":")
    if not sep or not family or not cluster:
        return None
    return family, cluster


def _scope_label(family: str, scope_kind: str, scope_key: str) -> str:
    if scope_kind == "cluster":
        return f"{family}/{scope_key}"
    return family


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


# Global (*) board fallback when no coupling row exists yet. Replication is
# seeded as separate (043); keep the UI aligned before/without the migration.
_DEFAULT_MODE_BY_FAMILY: dict[str, str] = {
    "backup_veeam_replication_classic": "separate",
    "backup_zerto_replication_classic": "separate",
    "backup_veeam_replication_hyperconverged": "separate",
    "backup_zerto_replication_hyperconverged": "separate",
}


def _mode_map(rows: list[dict[str, Any]], scope: str) -> dict[str, str]:
    """``family -> mode`` for one scope; ``inherit`` when no per-DC row exists."""
    explicit = {
        r["family"]: r["mode"] for r in _family_rows(rows) if r.get("dc_code") == scope
    }
    if scope != _DEFAULT_SCOPE:
        return {fam: explicit.get(fam, _INHERIT) for fam in _families(rows)}
    return {
        fam: explicit.get(fam, _DEFAULT_MODE_BY_FAMILY.get(fam, "auto"))
        for fam in _families(rows)
    }


def _cluster_mode_map(
    rows: list[dict[str, Any]],
    scope: str,
    clusters: list[tuple[str, str]],
) -> dict[str, str]:
    """``cluster card key -> mode``; ``inherit`` when the cluster has no row."""
    explicit = {
        (r["family"], r["scope_key"]): r["mode"]
        for r in rows
        if r.get("scope_kind") == "cluster" and r.get("dc_code") == scope
    }
    return {
        _cluster_key(fam, cluster): explicit.get((fam, cluster), _INHERIT)
        for fam, cluster in clusters
    }


def _default_map(rows: list[dict[str, Any]]) -> dict[str, str]:
    return {
        r["family"]: r["mode"]
        for r in _family_rows(rows)
        if r.get("dc_code") == _DEFAULT_SCOPE
    }


def _effective_family_map(rows: list[dict[str, Any]], scope: str) -> dict[str, str]:
    """What each family actually resolves to at ``scope`` — the DC row if there
    is one, otherwise the ``'*'`` row. Cluster cards show this as their fallback.
    """
    defaults = _default_map(rows)
    per_dc = _mode_map(rows, scope)
    return {
        fam: (mode if mode != _INHERIT else defaults.get(fam, "auto"))
        for fam, mode in per_dc.items()
    }


# ---------------------------------------------------------------------------
# board
# ---------------------------------------------------------------------------


def _card(
    card_key: str,
    family: str,
    mode: str,
    inherited: str | None,
    *,
    title: str | None = None,
    warning: str | None = None,
) -> html.Div:
    label = title or _FAMILY_LABELS.get(family, family)
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
    body: list[Any] = [
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
    ]
    if warning:
        body.append(
            dmc.Group(
                gap=4,
                mt=4,
                wrap="nowrap",
                align="flex-start",
                children=[
                    DashIconify(icon="solar:info-circle-bold-duotone", width=13, color="#B54708"),
                    dmc.Text(warning, size="xs", c="#B54708"),
                ],
            )
        )
    return html.Div(
        draggable="true",
        tabIndex=0,
        className="csc-card",
        **{
            "data-coupling-card": "1",
            "data-card-key": card_key,
            "data-family": family,
            "data-initial-mode": mode,
            "aria-label": f"{label} — {mode}. Use the arrow keys to move it between columns.",
        },
        children=body,
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


def _family_cards(rows: list[dict[str, Any]], scope: str) -> tuple[dict[str, str], dict[str, html.Div]]:
    assignment = _mode_map(rows, scope)
    defaults = _default_map(rows)
    cards = {
        fam: _card(
            fam,
            fam,
            mode,
            defaults.get(fam) if scope != _DEFAULT_SCOPE else None,
            warning=_FAMILY_WARNINGS.get(fam),
        )
        for fam, mode in assignment.items()
    }
    return assignment, cards


def _cluster_cards(
    rows: list[dict[str, Any]],
    scope: str,
    clusters: list[tuple[str, str]],
) -> tuple[dict[str, str], dict[str, html.Div]]:
    assignment = _cluster_mode_map(rows, scope, clusters)
    effective = _effective_family_map(rows, scope)
    cards = {
        key: _card(
            key,
            fam,
            assignment[key],
            effective.get(fam, "auto"),
            title=cluster,
        )
        for fam, cluster in clusters
        for key in [_cluster_key(fam, cluster)]
    }
    return assignment, cards


def _board(
    rows: list[dict[str, Any]],
    scope: str,
    *,
    detail: bool = False,
    clusters: list[tuple[str, str]] | None = None,
) -> Any:
    """Four drop zones; ``detail`` swaps family cards for cluster cards."""
    if detail:
        assignment, cards = _cluster_cards(rows, scope, clusters or [])
        if not cards:
            return dmc.Alert(
                "No host-based clusters returned for this DC, so there is nothing to "
                "set at cluster level. Klasik Mimari, Hyperconverged, and Replication "
                "Classic/HC use the same cluster lists; other families are aggregated "
                "and can only be set at environment level.",
                title="No clusters to show",
                color="gray",
                variant="light",
            )
        # 'inherit' means "no cluster row — follow the family", which is a real
        # choice at every scope, unlike the family board where '*' has nothing
        # above it to inherit from.
        zones = list(_ZONE_DEFS)
    else:
        assignment, cards = _family_cards(rows, scope)
        zones = [z for z in _ZONE_DEFS if z[0] != _INHERIT or scope != _DEFAULT_SCOPE]

    return dmc.SimpleGrid(
        cols={"base": 1, "md": 2, "lg": len(zones)},
        spacing="md",
        children=[
            _zone(
                mode,
                title,
                _INHERIT_SUBTITLE_CLUSTER if (detail and mode == _INHERIT) else subtitle,
                color,
                icon,
                [cards[key] for key, m in sorted(assignment.items()) if m == mode],
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
            {"name": "scope", "id": "scope_kind"},
            {"name": "cluster", "id": "scope_key"},
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
                                    gap="md",
                                    align="center",
                                    children=[
                                        dmc.Switch(
                                            id=_DETAIL_ID,
                                            label="Cluster detail",
                                            description="Needs a single DC — cluster names are DC-local.",
                                            checked=False,
                                            disabled=True,
                                            size="sm",
                                        ),
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
                dmc.Text(
                    "Cluster detail is available for Klasik Mimari and Hyperconverged — "
                    "the two environments whose sellable is computed host-by-host. A "
                    "cluster rule wins over its environment's rule and leaves untouched "
                    "clusters on the built-in behaviour.",
                    size="xs",
                    c="dimmed",
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


def _rebuild(
    scope: str, detail: bool = False,
) -> tuple[Any, dict[str, str], list[dict[str, Any]]]:
    rows, _error = _load_rows()
    if detail and scope != _DEFAULT_SCOPE:
        clusters = _clusters_for(scope)
        return (
            _board(rows, scope, detail=True, clusters=clusters),
            _cluster_mode_map(rows, scope, clusters),
            rows,
        )
    return _board(rows, scope), _mode_map(rows, scope), rows


@callback(
    Output(_BOARD_ID, "children"),
    Output(_STORE_ID, "data"),
    Output(_DETAIL_ID, "disabled"),
    Output(_DETAIL_ID, "checked"),
    Input(_SCOPE_ID, "value"),
    prevent_initial_call=True,
)
def _switch_scope(scope):
    scope = str(scope or _DEFAULT_SCOPE)
    # Switching scope always drops back to the environment board: the previous
    # DC's cluster cards mean nothing here, and leaving the switch on would show
    # a board whose card keys no longer match the store.
    board, state, _rows = _rebuild(scope, detail=False)
    return board, state, scope == _DEFAULT_SCOPE, False


@callback(
    Output(_BOARD_ID, "children", allow_duplicate=True),
    Output(_STORE_ID, "data", allow_duplicate=True),
    Input(_DETAIL_ID, "checked"),
    State(_SCOPE_ID, "value"),
    prevent_initial_call=True,
)
def _switch_detail(detail, scope):
    board, state, _rows = _rebuild(str(scope or _DEFAULT_SCOPE), detail=bool(detail))
    return board, state


@callback(
    Output(_BOARD_ID, "children", allow_duplicate=True),
    Output(_STORE_ID, "data", allow_duplicate=True),
    Output(_TABLE_ID, "data", allow_duplicate=True),
    Output("csc-msg", "children", allow_duplicate=True),
    Input("csc-reset", "n_clicks"),
    State(_SCOPE_ID, "value"),
    State(_DETAIL_ID, "checked"),
    prevent_initial_call=True,
)
def _reset(_n, scope, detail):
    board, state, rows = _rebuild(str(scope or _DEFAULT_SCOPE), detail=bool(detail))
    return board, state, rows, dmc.Alert("Board reloaded from the database.", color="gray", variant="light")


@callback(
    Output("csc-msg", "children"),
    Output(_BOARD_ID, "children", allow_duplicate=True),
    Output(_STORE_ID, "data", allow_duplicate=True),
    Output(_TABLE_ID, "data", allow_duplicate=True),
    Input("csc-save", "n_clicks"),
    State(_STORE_ID, "data"),
    State(_SCOPE_ID, "value"),
    State(_DETAIL_ID, "checked"),
    prevent_initial_call=True,
)
def _save(_n, state, scope, detail):
    scope = str(scope or _DEFAULT_SCOPE)
    detail = bool(detail) and scope != _DEFAULT_SCOPE
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

    # The board only ever shows one granularity at a time, so the store holds
    # either family keys or cluster keys — never both. Saving compares against
    # the matching rows so a cluster edit can never touch an environment rule.
    if detail:
        clusters = _clusters_for(scope)
        current = _cluster_mode_map(rows, scope, clusters)
        targets = {
            key: _split_cluster_key(key)
            for key in assignment
            if _split_cluster_key(key) is not None
        }
    else:
        current = _mode_map(rows, scope)
        targets = {key: None for key in assignment if not key.startswith(_CLUSTER_KEY_PREFIX)}

    def _scope_args(key: str) -> tuple[str, str, str]:
        parts = targets.get(key)
        if parts is None:
            return key, "family", ""
        family, cluster = parts
        return family, "cluster", cluster

    upserts = []
    deletes = []
    for key in sorted(targets):
        mode = assignment[key]
        family, scope_kind, scope_key = _scope_args(key)
        if mode == _INHERIT:
            if current.get(key) not in (None, _INHERIT):
                deletes.append((key, family, scope_kind, scope_key))
        elif current.get(key) != mode:
            upserts.append(
                {
                    "family": family,
                    "dc_code": scope,
                    "scope_kind": scope_kind,
                    "scope_key": scope_key,
                    "mode": mode,
                }
            )
    if not upserts and not deletes:
        return dmc.Alert("No changes to save.", color="gray", variant="light"), no_update, no_update, no_update

    try:
        if upserts:
            api.put_storage_couplings(upserts, updated_by=_current_username())
        for _key, family, scope_kind, scope_key in deletes:
            api.delete_storage_coupling(
                family, scope, scope_kind=scope_kind, scope_key=scope_key
            )
    except Exception as exc:  # noqa: BLE001 — surface the API error in the UI
        return (
            dmc.Alert(str(exc), title="Save failed", color="red", variant="light"),
            no_update,
            no_update,
            no_update,
        )

    board, new_state, new_rows = _rebuild(scope, detail=detail)
    changed = ", ".join(
        f"{_scope_label(r['family'], r['scope_kind'], r['scope_key'])}→{r['mode']}"
        for r in upserts
    )
    dropped = ", ".join(
        f"{_scope_label(family, scope_kind, scope_key)}→inherit"
        for _key, family, scope_kind, scope_key in deletes
    )
    summary = " · ".join(p for p in (changed, dropped) if p)
    return (
        dmc.Alert(
            f"Saved for scope '{scope}': {summary}. Sellable numbers refresh on the next dashboard load.",
            title="Saved",
            color="green",
            variant="light",
        ),
        board,
        new_state,
        new_rows,
    )
