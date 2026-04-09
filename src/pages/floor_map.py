"""
Floor map — unified building floor plan.

Layout model:
  - All halls live inside ONE floor boundary (the "building floor").
  - Halls are arranged in a 2-column grid of rooms, separated by wall lines.
  - Each hall is a labelled zone; racks sit inside it.
  - Aisle drawn between front/back rack rows within each hall.
"""

import math
import re
import plotly.graph_objects as go
from dash import html, dcc
import dash_mantine_components as dmc
from dash_iconify import DashIconify

# ── Rack unit dimensions ────────────────────────────────────────────────────
RACK_W = 22
RACK_H = 34
GAP_X  = 8
GAP_Y  = 10
AISLE_H = 30

# ── Hall zone padding (inside hall boundary) ────────────────────────────────
ZONE_PAD_X   = 22
ZONE_PAD_TOP = 14   # above racks
ZONE_PAD_BOT = 14   # below racks
ZONE_LABEL_H = 24   # hall name strip at top

# ── Floor-level padding (around all halls) ─────────────────────────────────
FLOOR_PAD = 28
HALL_COL_GAP = 0   # halls share walls → no gap between columns
HALL_ROW_GAP = 0   # halls share walls → no gap between rows

# ── Max halls per row in the floor grid ────────────────────────────────────
HALLS_PER_ROW = 2

# ── Status palette ─────────────────────────────────────────────────────────
STATUS_FILL   = {"active": "#17B26A", "planned": "#2E90FA", "inactive": "#F04438", "unknown": "#98A2B3"}
STATUS_DARK   = {"active": "#027A48", "planned": "#175CD3", "inactive": "#B42318", "unknown": "#667085"}


def _color(status):
    k = (status or "unknown").lower()
    return STATUS_FILL.get(k, STATUS_FILL["unknown"]), STATUS_DARK.get(k, STATUS_DARK["unknown"])


def _parse_row_col(identifier):
    if not identifier:
        return None, None
    m = re.match(r'^([A-Za-z]+)(\d+)$', str(identifier).strip())
    if m:
        col_str = m.group(1).upper()
        row = int(m.group(2))
        col = 0
        for ch in col_str:
            col = col * 26 + (ord(ch) - ord('A') + 1)
        return row, col
    return None, None


def _sort_key(rack):
    fid = rack.get("facility_id") or rack.get("name") or ""
    row, col = _parse_row_col(fid)
    return (0, row, col) if row is not None else (1, 0, 0)


# ── Compute dimensions for one hall zone ───────────────────────────────────

def _hall_dimensions(hall_racks):
    """Return (n_cols, n_rows_total, has_aisle, rows_set, cols_set, ungridded)."""
    grid, ungridded = {}, []
    for rack in hall_racks:
        fid = rack.get("facility_id") or rack.get("name") or ""
        row, col = _parse_row_col(fid)
        if row is not None:
            grid[(row, col)] = rack
        else:
            ungridded.append(rack)

    rows_set = sorted(set(r for r, c in grid)) if grid else []
    cols_set = sorted(set(c for r, c in grid)) if grid else []
    n_rows_grid = len(rows_set)
    n_cols_grid  = len(cols_set)

    n_ung_per_row = max(n_cols_grid, min(len(ungridded), 10)) if ungridded else 0
    if ungridded and n_ung_per_row == 0:
        n_ung_per_row = min(len(ungridded), 10)
    n_ung_rows = math.ceil(len(ungridded) / n_ung_per_row) if ungridded and n_ung_per_row else 0

    n_rows_total = n_rows_grid + n_ung_rows
    n_cols_total = max(n_cols_grid, n_ung_per_row, 1)

    has_aisle    = n_rows_total >= 2
    aisle_after  = n_rows_total // 2 if has_aisle else 0

    if has_aisle:
        inner_h = n_rows_total * (RACK_H + GAP_Y) - GAP_Y + AISLE_H
    else:
        inner_h = RACK_H

    zone_w = n_cols_total * (RACK_W + GAP_X) - GAP_X + ZONE_PAD_X * 2
    zone_h = ZONE_LABEL_H + ZONE_PAD_TOP + inner_h + ZONE_PAD_BOT

    return dict(
        zone_w=zone_w, zone_h=zone_h,
        n_rows_grid=n_rows_grid, n_cols_total=n_cols_total,
        rows_set=rows_set, cols_set=cols_set,
        has_aisle=has_aisle, aisle_after=aisle_after,
        ungridded=ungridded, n_ung_per_row=n_ung_per_row,
        grid=grid,
    )


def _draw_rack(fig, rx, ry, status, name, rack_data, dc_id=""):
    fill, dark = _color(status)
    rid        = rack_data.get("id") or ""
    u          = rack_data.get("u_height") or 0
    pwr        = rack_data.get("kabin_enerji") or "—"
    rh         = rack_data.get("hall_name") or "—"
    rack_type  = rack_data.get("rack_type") or "—"
    serial     = rack_data.get("serial") or "—"

    # Shadow
    fig.add_shape(type="rect",
        x0=rx+2, y0=ry-2.5, x1=rx+RACK_W+2, y1=ry+RACK_H-2.5,
        fillcolor="rgba(0,0,0,0.10)", line=dict(color="rgba(0,0,0,0)", width=0),
        layer="below")
    # Body
    fig.add_shape(type="rect",
        x0=rx, y0=ry, x1=rx+RACK_W, y1=ry+RACK_H,
        fillcolor=fill, line=dict(color=dark, width=1.3))
    # Gloss highlight
    fig.add_shape(type="rect",
        x0=rx+1.5, y0=ry+RACK_H*0.52, x1=rx+RACK_W-1.5, y1=ry+RACK_H-1.5,
        fillcolor="rgba(255,255,255,0.15)", line=dict(color="rgba(0,0,0,0)", width=0))
    # Front panel bar
    fig.add_shape(type="rect",
        x0=rx, y0=ry, x1=rx+RACK_W, y1=ry+5.5,
        fillcolor=dark, line=dict(color="rgba(0,0,0,0)", width=0))
    # LED
    led_fill = "#ECFDF3" if status == "active" else "rgba(255,255,255,0.65)"
    fig.add_shape(type="circle",
        x0=rx+3, y0=ry+1.4, x1=rx+5, y1=ry+3.4,
        fillcolor=led_fill, line=dict(color="rgba(0,0,0,0)", width=0))
    # Hover trace
    fig.add_trace(go.Scatter(
        x=[rx + RACK_W / 2], y=[ry + RACK_H / 2 + 2],
        mode="markers+text",
        marker=dict(size=1, color="rgba(0,0,0,0)"),
        text=[name[:6]],
        textposition="middle center",
        textfont=dict(size=6.5, color="white", family="DM Sans, sans-serif"),
        hovertemplate=(
            f"<b>{name}</b><br>Hall: {rh}<br>Status: {status.title()}<br>"
            f"U: {u}U<br>Power: {pwr}<br>Type: {rack_type}<extra></extra>"
        ),
        customdata=[[rid, name, status, u, pwr, rh, rack_type, serial, dc_id]],
        showlegend=False, name=name,
    ))


def _draw_hall_zone(fig, hx, hy, hall_name, dims, dc_id=""):
    """Draw one hall zone starting at canvas coords (hx, hy)."""
    zw = dims["zone_w"]
    zh = dims["zone_h"]

    # ── Zone background (light grey floor)
    fig.add_shape(type="rect",
        x0=hx, y0=hy, x1=hx+zw, y1=hy+zh,
        fillcolor="rgba(248,249,252,1)",
        line=dict(color="rgba(208,213,221,1)", width=1.5),
        layer="below")

    # ── Hall label strip at top
    fig.add_shape(type="rect",
        x0=hx, y0=hy+zh-ZONE_LABEL_H, x1=hx+zw, y1=hy+zh,
        fillcolor="rgba(242,244,247,1)",
        line=dict(color="rgba(0,0,0,0)", width=0),
        layer="below")
    fig.add_shape(type="line",
        x0=hx, y0=hy+zh-ZONE_LABEL_H, x1=hx+zw, y1=hy+zh-ZONE_LABEL_H,
        line=dict(color="rgba(208,213,221,0.9)", width=1))
    fig.add_annotation(
        text=f"<b>{hall_name}</b>",
        x=hx + zw / 2, y=hy + zh - ZONE_LABEL_H / 2,
        xanchor="center", yanchor="middle", showarrow=False,
        font=dict(size=10, color="#344054", family="DM Sans, sans-serif"))

    grid         = dims["grid"]
    rows_set     = dims["rows_set"]
    cols_set     = dims["cols_set"]
    n_rows_grid  = dims["n_rows_grid"]
    has_aisle    = dims["has_aisle"]
    aisle_after  = dims["aisle_after"]
    ungridded    = dims["ungridded"]
    n_ung_per_row = dims["n_ung_per_row"]
    col_idx_map  = {c: i for i, c in enumerate(cols_set)}

    def row_y(ri):
        base = hy + ZONE_PAD_BOT + ri * (RACK_H + GAP_Y)
        if has_aisle and ri >= aisle_after:
            base += AISLE_H
        return base

    # ── Aisle stripe
    if has_aisle:
        ay = hy + ZONE_PAD_BOT + aisle_after * (RACK_H + GAP_Y)
        fig.add_shape(type="rect",
            x0=hx + ZONE_PAD_X - 4, y0=ay,
            x1=hx + zw - ZONE_PAD_X + 4, y1=ay + AISLE_H - 2,
            fillcolor="rgba(240,242,247,0.9)",
            line=dict(color="rgba(200,206,215,0.55)", width=1, dash="dot"),
            layer="below")
        fig.add_annotation(
            text="A I S L E",
            x=hx + zw / 2, y=ay + AISLE_H / 2 - 1,
            xanchor="center", yanchor="middle", showarrow=False,
            font=dict(size=6, color="#B0B7C3", family="DM Sans, sans-serif"))

    # ── Grid racks
    for row_i, row_val in enumerate(rows_set):
        ry_base = row_y(row_i)
        for col_val in cols_set:
            rack = grid.get((row_val, col_val))
            if not rack:
                continue
            ci = col_idx_map[col_val]
            rx = hx + ZONE_PAD_X + ci * (RACK_W + GAP_X)
            status = (rack.get("status") or "unknown").lower()
            _draw_rack(fig, rx, ry_base, status, str(rack.get("name") or "?"), rack, dc_id=dc_id)

    # ── Ungridded racks
    for i, rack in enumerate(ungridded):
        ci = i % n_ung_per_row
        ri = n_rows_grid + i // n_ung_per_row
        ry_base = row_y(ri)
        rx = hx + ZONE_PAD_X + ci * (RACK_W + GAP_X)
        status = (rack.get("status") or "unknown").lower()
        _draw_rack(fig, rx, ry_base, status, str(rack.get("name") or "?"), rack)


# ── Main figure builder ─────────────────────────────────────────────────────

def build_floor_map_figure(racks, dc_id=""):
    halls_raw = {}
    for rack in racks:
        hall = rack.get("hall_name") or "Main Hall"
        halls_raw.setdefault(hall, []).append(rack)
    for h in halls_raw:
        halls_raw[h].sort(key=_sort_key)

    hall_list = sorted(halls_raw.items())   # [(name, racks), ...]
    n_halls   = len(hall_list)

    # Pre-compute each hall's zone dimensions
    hall_dims = [(name, rack_list, _hall_dimensions(rack_list))
                 for name, rack_list in hall_list]

    # Arrange halls in rows of HALLS_PER_ROW
    n_cols_layout = min(n_halls, HALLS_PER_ROW)
    n_rows_layout = math.ceil(n_halls / n_cols_layout)

    # Normalise column widths and row heights per grid cell
    col_widths = []
    row_heights = []
    for gr in range(n_rows_layout):
        max_h = 0
        for gc in range(n_cols_layout):
            idx = gr * n_cols_layout + gc
            if idx < n_halls:
                max_h = max(max_h, hall_dims[idx][2]["zone_h"])
        row_heights.append(max_h)

    for gc in range(n_cols_layout):
        max_w = 0
        for gr in range(n_rows_layout):
            idx = gr * n_cols_layout + gc
            if idx < n_halls:
                max_w = max(max_w, hall_dims[idx][2]["zone_w"])
        col_widths.append(max_w)

    total_inner_w = sum(col_widths)  + HALL_COL_GAP * (n_cols_layout - 1)
    total_inner_h = sum(row_heights) + HALL_ROW_GAP * (n_rows_layout - 1)
    floor_w = total_inner_w + FLOOR_PAD * 2
    floor_h = total_inner_h + FLOOR_PAD * 2

    fig = go.Figure()

    # ── Outer floor shadow
    fig.add_shape(type="rect",
        x0=4, y0=-4, x1=floor_w+4, y1=floor_h-4,
        fillcolor="rgba(16,24,40,0.06)",
        line=dict(color="rgba(0,0,0,0)", width=0), layer="below")

    # ── Outer floor boundary (the building)
    fig.add_shape(type="rect",
        x0=0, y0=0, x1=floor_w, y1=floor_h,
        fillcolor="rgba(255,255,255,1)",
        line=dict(color="rgba(152,162,179,1)", width=2),
        layer="below")

    # ── Place each hall zone
    for idx, (hall_name, _, dims) in enumerate(hall_dims):
        gr = idx // n_cols_layout
        gc = idx %  n_cols_layout

        hx = FLOOR_PAD + sum(col_widths[:gc]) + HALL_COL_GAP * gc
        # Zones stack from top → bottom; y=0 is bottom in plotly, so invert
        hy_from_top = FLOOR_PAD + sum(row_heights[:gr]) + HALL_ROW_GAP * gr
        hy = floor_h - hy_from_top - dims["zone_h"]

        _draw_hall_zone(fig, hx, hy, hall_name, dims, dc_id=dc_id)

    # ── Empty state
    if not racks:
        fig.add_annotation(
            text="No rack data available", xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=16, color="#98A2B3", family="DM Sans"))

    fig.update_layout(
        xaxis=dict(visible=False, showgrid=False, zeroline=False,
                   range=[-10, floor_w + 30]),
        yaxis=dict(visible=False, showgrid=False, zeroline=False,
                   scaleanchor="x", range=[-20, floor_h + 20]),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=20, r=20, t=20, b=20),
        dragmode="pan",
        height=560,
        hoverlabel=dict(
            bgcolor="rgba(255,255,255,0.98)",
            bordercolor="rgba(208,213,221,1)",
            font=dict(family="DM Sans, sans-serif", size=12, color="#101828"),
            align="left"),
    )
    return fig


# ── Layout builder ──────────────────────────────────────────────────────────

def build_floor_map_layout(dc_id, dc_name, racks):
    active_count   = sum(1 for r in racks if (r.get("status") or "").lower() == "active")
    planned_count  = sum(1 for r in racks if (r.get("status") or "").lower() == "planned")
    inactive_count = len(racks) - active_count - planned_count
    fig = build_floor_map_figure(racks, dc_id=dc_id)

    halls = {}
    for r in racks:
        h = r.get("hall_name") or "Main Hall"
        halls.setdefault(h, 0)
        halls[h] += 1

    stat_badges = [
        dmc.Badge(
            dmc.Group(gap=5, align="center", children=[
                html.Span(className="fm-status-dot fm-dot-active"),
                f"{active_count} Active",
            ]),
            color="green", variant="light", size="sm",
        ),
    ]
    if inactive_count > 0:
        stat_badges.append(dmc.Badge(
            dmc.Group(gap=5, align="center", children=[
                html.Span(className="fm-status-dot fm-dot-inactive"),
                f"{inactive_count} Inactive",
            ]),
            color="red", variant="light", size="sm",
        ))
    if planned_count > 0:
        stat_badges.append(dmc.Badge(
            dmc.Group(gap=5, align="center", children=[
                html.Span(className="fm-status-dot fm-dot-planned"),
                f"{planned_count} Planned",
            ]),
            color="blue", variant="light", size="sm",
        ))
    hall_badges = [
        dmc.Badge(
            dmc.Group(gap=4, align="center", children=[
                DashIconify(icon="solar:map-point-bold-duotone",
                            width=12, color="#667085"),
                f"{h}  ·  {c}",
            ]),
            color="gray", variant="light", size="sm",
        )
        for h, c in sorted(halls.items())
    ]

    return html.Div(
        className="floor-map-page",
        children=[
            # ── Header
            html.Div(
                className="floor-map-header",
                children=[
                    dmc.Group(align="center", gap="md", children=[
                        dmc.ActionIcon(
                            DashIconify(icon="solar:arrow-left-linear", width=18),
                            id="back-to-global-btn",
                            variant="subtle", color="gray",
                            size="lg", radius="md",
                        ),
                        html.Div(children=[
                            dmc.Group(gap="xs", align="center", children=[
                                dmc.ThemeIcon(
                                    DashIconify(icon="solar:buildings-3-bold-duotone",
                                                width=18),
                                    size="md", radius="md",
                                    variant="light", color="violet",
                                ),
                                dmc.Text(dc_name, fw=700, size="lg", c="#101828"),
                            ]),
                            dmc.Text("Floor Map — Rack Layout",
                                     size="xs", c="#667085", fw=500),
                        ]),
                    ]),
                    dmc.Group(gap="xs", children=[
                        *stat_badges,
                        html.Div(style={"width": "1px", "height": "20px",
                                        "background": "#EAECF0", "margin": "0 4px"}),
                        *hall_badges,
                    ]),
                ],
            ),

            # ── Body
            dmc.Grid(
                gutter="lg", mt="md",
                children=[
                    dmc.GridCol(
                        span=8,
                        children=[
                            dmc.Paper(
                                radius="xl",
                                className="floor-map-canvas-wrap",
                                children=[
                                    dcc.Graph(
                                        id="floor-map-graph",
                                        figure=fig,
                                        config={"scrollZoom": True,
                                                "displayModeBar": False},
                                        style={"height": "560px"},
                                    ),
                                ],
                            ),
                            # Legend
                            dmc.Group(
                                gap="lg", mt="sm", px="sm",
                                children=[
                                    dmc.Group(gap=6, align="center", children=[
                                        html.Div(className="fm-legend-swatch fm-swatch-active"),
                                        dmc.Text("Active", size="xs", c="#667085"),
                                    ]),
                                    dmc.Group(gap=6, align="center", children=[
                                        html.Div(className="fm-legend-swatch fm-swatch-inactive"),
                                        dmc.Text("Inactive", size="xs", c="#667085"),
                                    ]),
                                    dmc.Group(gap=6, align="center", children=[
                                        html.Div(className="fm-legend-swatch fm-swatch-planned"),
                                        dmc.Text("Planned", size="xs", c="#667085"),
                                    ]),
                                    dmc.Group(gap=6, align="center", children=[
                                        html.Div(className="fm-legend-swatch fm-swatch-unknown"),
                                        dmc.Text("Unknown", size="xs", c="#667085"),
                                    ]),
                                    dmc.Text(
                                        "Scroll to zoom · Drag to pan · Click rack to inspect",
                                        size="xs", c="#98A2B3", ml="auto",
                                    ),
                                ],
                            ),
                        ],
                    ),
                    dmc.GridCol(
                        span=4,
                        children=[
                            dmc.Paper(
                                id="floor-map-rack-detail",
                                radius="xl", p="lg",
                                className="floor-map-detail-panel",
                                children=[
                                    html.Div(
                                        className="floor-map-detail-empty",
                                        children=[
                                            html.Div(
                                                className="fm-empty-icon-wrap",
                                                children=[
                                                    DashIconify(
                                                        icon="solar:server-square-linear",
                                                        width=36, color="#D0D5DD",
                                                    ),
                                                ],
                                            ),
                                            dmc.Text("Click a rack to inspect",
                                                     c="#98A2B3", size="sm",
                                                     mt="md", fw=500),
                                            dmc.Text("Hover over racks to preview details",
                                                     c="#D0D5DD", size="xs", mt=4),
                                        ],
                                    )
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )
