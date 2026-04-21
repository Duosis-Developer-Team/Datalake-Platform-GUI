import plotly.graph_objects as go

# J1. Global Premium Theme
_PREMIUM_FONT = dict(
    family="DM Sans, sans-serif",
    color="#2B3674",
    size=12,
)

_PREMIUM_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=_PREMIUM_FONT,
    hoverlabel=dict(
        bgcolor="rgba(255,255,255,0.97)",
        bordercolor="rgba(67, 24, 255, 0.12)",
        font=dict(family="DM Sans", size=12, color="#2B3674"),
    ),
)

_LEGEND_STYLE = dict(
    orientation="h",
    yanchor="bottom",
    y=-0.15,
    xanchor="center",
    x=0.5,
    font=dict(size=11, family="DM Sans", color="#A3AED0"),
    bgcolor="rgba(0,0,0,0)",
)
_LEGEND_MINIMAL = dict(
    orientation="h",
    yanchor="bottom",
    y=-0.12,
    xanchor="center",
    x=0.5,
    font=dict(size=9, family="DM Sans", color="#A3AED0"),
    bgcolor="rgba(0,0,0,0)",
)


def _resolve_legend(show_legend):
    """show_legend: bool | 'minimal' | None — None/false hides legend."""
    if show_legend is None or show_legend is False:
        return False, None
    if show_legend == "minimal":
        return True, _LEGEND_MINIMAL
    return True, _LEGEND_STYLE


def create_gradient_area_chart(df, x_col, y_col, title, show_legend=True):
    show, leg = _resolve_legend(show_legend)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df[x_col], y=df[y_col], mode='lines', fill='tozeroy',
        line=dict(width=3, color='#4318FF'),
        fillcolor='rgba(67, 24, 255, 0.1)',
        name=str(y_col),
    ))
    layout_updates = dict(
        title=dict(text=title, font=dict(size=14, color='#2B3674', family="DM Sans")),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        showlegend=show,
        margin=dict(l=0, r=0, t=30, b=24 if show else 0),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=True),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        hovermode="x unified",
    )
    if show and leg:
        layout_updates["legend"] = leg
    fig.update_layout(**layout_updates)
    return fig

def create_bar_chart(data, x_col, y_col, title, color="#4318FF", height=250, show_legend=True):
    fig = go.Figure()
    # Data bir dict gelirse listeye çevir, DataFrame gelirse sütunu al
    x_data = data[x_col] if isinstance(data, dict) else data[x_col].tolist()
    y_data = data[y_col] if isinstance(data, dict) else data[y_col].tolist()

    fig.add_trace(go.Bar(
        x=x_data, y=y_data,
        marker_color=color,
        name=title
    ))
    
    show, leg = _resolve_legend(show_legend)
    layout_updates = dict(
        title=dict(text=title, font=dict(family="DM Sans, sans-serif", size=16, color="#2B3674", weight=700)),
        margin=dict(l=20, r=20, t=40, b=36 if show else 20),
        height=height,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        showlegend=show,
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=True),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=True),
        font=dict(family="DM Sans, sans-serif", color="#A3AED0"),
    )
    if show and leg:
        layout_updates["legend"] = leg
    fig.update_layout(**layout_updates)
    return fig


def create_usage_donut_chart(value, label, color="#4318FF"):
    """Donut chart for resource usage — kept for dc_view.py compatibility."""
    try:
        val = float(value)
    except (TypeError, ValueError):
        val = 0.0
    val = max(0.0, min(100.0, val))
    remaining = 100.0 - val

    fig = go.Figure(data=[go.Pie(
        values=[val, remaining],
        labels=["Used", "Free"],
        hole=0.82,
        marker=dict(
            colors=[color, "#EEF2FF"],
            line=dict(color="rgba(0,0,0,0)", width=0),
        ),
        sort=False,
        textinfo="none",
        hoverinfo="skip",
        direction="clockwise",
    )])

    text_val = f"{val:.1f}%" if val < 10 else f"<b>{int(val)}%</b>"
    fig.update_layout(
        annotations=[dict(
            text=text_val,
            x=0.5,
            y=0.5,
            xanchor="center",
            yanchor="middle",
            font=dict(size=32, color="#1a1b41", family="DM Sans"),
            showarrow=False,
        )],
        title=dict(
            text=f"<b>{label}</b>",
            x=0.5,
            xanchor="center",
            font=dict(size=12, color="#A3AED0", family="DM Sans"),
        ),
        showlegend=False,
        margin=dict(l=8, r=8, t=44, b=8),
        height=180,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def create_avg_max_donut_chart(avg_val, max_val, label, color="#4318FF"):
    """Donut emphasizing peak utilization (max) with avg as secondary annotation (capacity planning)."""
    try:
        avg_v = float(avg_val)
        max_v = float(max_val)
    except (TypeError, ValueError):
        avg_v, max_v = 0.0, 0.0
    avg_v = max(0.0, min(100.0, avg_v))
    max_v = max(0.0, min(100.0, max_v))
    remaining = 100.0 - max_v
    fig = go.Figure(
        data=[
            go.Pie(
                values=[max_v, remaining],
                labels=["Peak used", "Headroom"],
                hole=0.82,
                marker=dict(
                    colors=[color, "#EEF2FF"],
                    line=dict(color="rgba(0,0,0,0)", width=0),
                ),
                sort=False,
                textinfo="none",
                hovertemplate="<b>%{label}</b>: %{value:.1f}%<extra></extra>",
                direction="clockwise",
            )
        ]
    )
    fig.update_layout(
        annotations=[
            dict(
                text=f"<b>{int(max_v)}%</b><br><span style='font-size:11px;color:#A3AED0;font-weight:400'>avg {int(avg_v)}%</span>",
                x=0.5,
                y=0.5,
                xanchor="center",
                yanchor="middle",
                font=dict(size=26, color="#2B3674", family="DM Sans"),
                showarrow=False,
            )
        ],
        title=dict(
            text=f"<b>{label}</b>",
            x=0.5,
            xanchor="center",
            font=dict(size=12, color="#A3AED0", family="DM Sans"),
        ),
        showlegend=False,
        margin=dict(l=8, r=8, t=44, b=8),
        height=180,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def create_stacked_bar_chart(labels, series_dict, title, height=300):
    """Stacked bar chart: labels on x, multiple series stacked. series_dict e.g. {'Nutanix': [1,2], 'VMware': [3,4], 'IBM': [0,1]}."""
    fig = go.Figure()
    colors = ["#4318FF", "#05CD99", "#FFB547"]
    for i, (name, values) in enumerate(series_dict.items()):
        fig.add_trace(go.Bar(
            x=labels,
            y=values,
            name=name,
            marker_color=colors[i % len(colors)],
        ))
    fig.update_layout(
        barmode="stack",
        title=dict(text=title, font=dict(size=14, color="#2B3674", family="DM Sans")),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=20, r=20, t=50, b=40),
        height=height,
        xaxis=dict(showgrid=False, zeroline=False),
        yaxis=dict(showgrid=False, zeroline=False),
        font=dict(family="DM Sans", color="#A3AED0"),
    )
    return fig


def create_grouped_bar_chart(labels, series_dict, title, height=380):
    """Executive horizontal grouped bar chart with avg reference line and unified hover."""
    fig = go.Figure()
    colors     = ["#4318FF",              "#05CD99"]
    colors_dim = ["rgba(67,24,255,0.55)", "rgba(5,205,153,0.55)"]

    all_vals = [v for vals in series_dict.values() for v in vals if v]
    avg = (sum(all_vals) / len(all_vals)) if all_vals else 0

    for i, (name, values) in enumerate(series_dict.items()):
        fig.add_trace(go.Bar(
            y=labels,
            x=values,
            name=name,
            orientation="h",
            marker=dict(
                color=colors[i % len(colors)],
                opacity=0.85,
                line=dict(color="rgba(0,0,0,0)", width=0),
            ),
            hovertemplate=f"<b>%{{y}}</b><br>{name}: %{{x:,}}<extra></extra>",
        ))

    # Sistem ortalaması referans çizgisi
    fig.add_vline(
        x=avg,
        line_dash="dot",
        line_color="rgba(67, 24, 255, 0.35)",
        line_width=1.5,
        annotation_text=f"Avg: {avg:,.0f}",
        annotation_position="top",
        annotation_font=dict(family="DM Sans", size=11, color="rgba(67,24,255,0.7)"),
    )

    fig.update_layout(
        barmode="group",
        hovermode="y unified",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.12,
            xanchor="center",
            x=0.5,
            font=dict(family="DM Sans", size=12, color="#2B3674"),
            bgcolor="rgba(0,0,0,0)",
        ),
        margin=dict(l=10, r=20, t=24, b=50),
        height=height,
        bargap=0.15,
        bargroupgap=0.06,
        xaxis=dict(
            showgrid=False,
            zeroline=False,
            showticklabels=False,
            tickfont=dict(family="DM Sans", size=11, color="#A3AED0"),
        ),
        yaxis=dict(
            showgrid=False,
            zeroline=False,
            tickfont=dict(family="DM Sans", size=13, color="#2B3674", weight=600),
            autorange="reversed",
        ),
        hoverlabel=dict(
            bgcolor="rgba(255,255,255,0.95)",
            bordercolor="rgba(67,24,255,0.2)",
            font=dict(family="DM Sans", size=12, color="#2B3674"),
        ),
        font=dict(family="DM Sans", color="#A3AED0"),
    )

    # Yuvarlak bar köşeleri — Plotly >= 5.12
    try:
        fig.update_traces(marker_cornerradius=6)
    except Exception:
        pass

    return fig


def create_storage_breakdown_chart(labels, used_series, free_series, height=None):
    """
    Premium stacked horizontal bar chart for storage capacity breakdown.
    Each row = one storage system; bar split into Used (indigo) + Free (light).
    Values displayed as TB/PB labels inside bars when space permits.
    """
    from src.utils.format_units import smart_storage as _smart

    n = len(labels)
    computed_height = max(120, n * 64 + 80) if height is None else height

    used_text = [_smart(v) if v >= 10 else "" for v in used_series]
    free_text = [_smart(v) if v >= 10 else "" for v in free_series]

    fig = go.Figure()

    # Used — indigo solid
    fig.add_trace(go.Bar(
        y=labels,
        x=used_series,
        name="Used",
        orientation="h",
        marker=dict(color="#4318FF", opacity=0.90),
        text=used_text,
        textposition="inside",
        insidetextanchor="middle",
        textfont=dict(family="DM Sans", size=11, color="rgba(255,255,255,0.9)"),
        hovertemplate="<b>%{y}</b><br>Used: %{customdata}<extra></extra>",
        customdata=[_smart(v) for v in used_series],
    ))

    # Free — soft indigo/grey
    fig.add_trace(go.Bar(
        y=labels,
        x=free_series,
        name="Free",
        orientation="h",
        marker=dict(color="#E9EDF7", opacity=1.0),
        text=free_text,
        textposition="inside",
        insidetextanchor="middle",
        textfont=dict(family="DM Sans", size=11, color="#A3AED0"),
        hovertemplate="<b>%{y}</b><br>Free: %{customdata}<extra></extra>",
        customdata=[_smart(v) for v in free_series],
    ))

    # Usage % annotation on the right of each bar
    totals = [u + f for u, f in zip(used_series, free_series)]
    for i, (lbl, u, t) in enumerate(zip(labels, used_series, totals)):
        pct = (u / t * 100) if t > 0 else 0
        color = "#EE5D50" if pct >= 80 else "#FFB547" if pct >= 60 else "#05CD99"
        fig.add_annotation(
            x=t,
            y=lbl,
            text=f"<b>{pct:.1f}%</b>",
            showarrow=False,
            xanchor="left",
            xshift=8,
            font=dict(family="DM Sans", size=12, color=color),
            xref="x",
            yref="y",
        )

    fig.update_layout(
        barmode="stack",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            font=dict(family="DM Sans", size=12, color="#2B3674"),
            bgcolor="rgba(0,0,0,0)",
            traceorder="normal",
        ),
        margin=dict(l=10, r=60, t=30, b=10),
        height=computed_height,
        bargap=0.3,
        xaxis=dict(
            showgrid=False,
            zeroline=False,
            showticklabels=False,
            range=[0, max(totals) * 1.12] if totals else [0, 1],
        ),
        yaxis=dict(
            showgrid=False,
            zeroline=False,
            tickfont=dict(family="DM Sans", size=13, color="#2B3674", weight=600),
            autorange="reversed",
        ),
        hoverlabel=dict(
            bgcolor="rgba(255,255,255,0.95)",
            bordercolor="rgba(67,24,255,0.2)",
            font=dict(family="DM Sans", size=12, color="#2B3674"),
        ),
        font=dict(family="DM Sans", color="#A3AED0"),
    )

    try:
        fig.update_traces(marker_cornerradius=6)
    except Exception:
        pass

    return fig


def create_horizontal_bar_chart(labels, values, title, color="#4318FF", height=340, show_legend=True):
    """Executive horizontal bar chart (single series)."""
    labels = labels or []
    values = values or []
    x_data = [float(v or 0) for v in values]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y=labels,
            x=x_data,
            orientation="h",
            marker=dict(
                color=color,
                opacity=0.9,
                line=dict(color="rgba(0,0,0,0)", width=0),
            ),
            hovertemplate="<b>%{y}</b><br>%{x:,.2f}<extra></extra>",
            name=title,
        )
    )

    show, leg = _resolve_legend(show_legend)
    layout_updates = dict(
        title=dict(text=title, font=dict(size=14, color="#2B3674", family="DM Sans", weight=700)),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=show,
        margin=dict(l=10, r=20, t=40, b=48 if show else 40),
        height=height,
        bargap=0.18,
        bargroupgap=0.06,
        xaxis=dict(
            showgrid=False,
            zeroline=False,
            showticklabels=False,
        ),
        yaxis=dict(
            showgrid=False,
            zeroline=False,
            tickfont=dict(family="DM Sans", size=12, color="#2B3674", weight=600),
        ),
        font=dict(family="DM Sans", color="#A3AED0"),
    )
    if show and leg:
        layout_updates["legend"] = leg
    fig.update_layout(**layout_updates)
    try:
        fig.update_traces(marker_cornerradius=6)
    except Exception:
        pass

    return fig


def create_premium_horizontal_bar_chart(
    labels, values, title, unit_suffix="Gbps", height=340, show_legend=True
):
    """
    Premium horizontal bar chart.
    - Color gradient by value (low=lavender, high=indigo)
    - Value labels on the right of each bar
    - Rounded corners, hover with interface + value
    """
    labels = labels or []
    values = values or []
    x_data = [float(v or 0) for v in values]

    max_val = max(x_data) or 1.0

    norm = [v / max_val for v in x_data]

    def lerp_hex(t):
        r = int(0xC4 + (0x43 - 0xC4) * t)
        g = int(0xB5 + (0x18 - 0xB5) * t)
        b = int(0xFD + (0xFF - 0xFD) * t)
        return f"#{r:02X}{g:02X}{b:02X}"

    bar_colors = [lerp_hex(n) for n in norm]
    text_labels = [f"{v:.2f} {unit_suffix}" if v > 0 else "" for v in x_data]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y=labels,
            x=x_data,
            orientation="h",
            marker=dict(
                color=bar_colors,
                opacity=1.0,
                line=dict(color="rgba(0,0,0,0)", width=0),
            ),
            text=text_labels,
            textposition="outside",
            textfont=dict(size=11, color="#2B3674", family="DM Sans", weight=600),
            hovertemplate="<b>%{y}</b><br>P95: <b>%{x:.3f} " + unit_suffix + "</b><extra></extra>",
            name="",
        )
    )

    try:
        fig.update_traces(marker_cornerradius=8)
    except Exception:
        pass

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        margin=dict(l=10, r=90, t=10, b=10),
        height=height,
        bargap=0.30,
        xaxis=dict(
            showgrid=False,
            zeroline=False,
            showticklabels=False,
            range=[0, max_val * 1.30],
        ),
        yaxis=dict(
            showgrid=False,
            zeroline=False,
            tickfont=dict(family="DM Sans", size=12, color="#2B3674", weight=600),
            categoryorder="total ascending",
        ),
        font=dict(family="DM Sans", color="#A3AED0"),
        hoverlabel=dict(
            bgcolor="rgba(255,255,255,0.97)",
            bordercolor="rgba(67, 24, 255, 0.15)",
            font=dict(family="DM Sans", size=12, color="#2B3674"),
        ),
    )
    return fig


def create_capacity_area_chart(timestamps, used, total, title, height=260, show_legend=True):
    """
    Capacity planning trend chart.
    Inputs are used/total bytes arrays; we plot utilization percentage over time.
    """
    x = list(timestamps or [])
    used_vals = [float(v or 0) for v in (used or [])]
    total_vals = [float(v or 0) for v in (total or [])]

    y_pct: list[float] = []
    for u, t in zip(used_vals, total_vals):
        if t > 0:
            y_pct.append(min(u / t * 100.0, 100.0))
        else:
            y_pct.append(0.0)

    # A1. Dynamic Y-axis zoom around data
    if y_pct:
        y_min = max(0.0, min(y_pct) - 8.0)
        y_max = min(105.0, max(y_pct) + 5.0)
    else:
        y_min, y_max = 0.0, 105.0

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x,
            y=y_pct,
            mode="lines",
            fill="tozeroy",
            line=dict(
                width=2.5,
                color="#4318FF",
                shape="spline",
                smoothing=1.3,
            ),
            fillgradient=dict(
                type="vertical",
                colorscale=[
                    [0.0, "rgba(67, 24, 255, 0.18)"],
                    [1.0, "rgba(67, 24, 255, 0.01)"],
                ],
            ),
            fillcolor="rgba(67, 24, 255, 0.10)",
            hovertemplate="<b>%{x|%b %d, %Y}</b><br>Utilization: <b>%{y:.1f}%</b><extra></extra>",
            name="Utilization %",
        )
    )

    # A2. Last point marker — "current value" highlight
    if x and y_pct:
        fig.add_trace(
            go.Scatter(
                x=[x[-1]],
                y=[y_pct[-1]],
                mode="markers",
                marker=dict(
                    size=10,
                    color="#4318FF",
                    line=dict(color="white", width=2),
                    symbol="circle",
                ),
                hovertemplate=f"<b>Current:</b> {y_pct[-1]:.1f}%<extra></extra>",
                showlegend=False,
            )
        )

    # M2. 80% threshold reference line
    fig.add_hline(
        y=80,
        line_dash="dot",
        line_color="#FFB547",
        line_width=1.5,
        opacity=0.7,
        annotation_text="80% threshold",
        annotation_position="right",
        annotation=dict(
            font=dict(size=10, color="#FFB547", family="DM Sans"),
            bgcolor="rgba(255,255,255,0.85)",
            bordercolor="rgba(255,181,71,0.3)",
            borderwidth=1,
            borderpad=4,
        ),
    )

    # A3. Daily vertical separator lines
    if x:
        seen_days: set = set()
        for ts in x:
            try:
                day = ts[:10] if isinstance(ts, str) else ts.strftime("%Y-%m-%d")
                if day not in seen_days:
                    seen_days.add(day)
                    fig.add_vline(
                        x=ts,
                        line_dash="dot",
                        line_color="rgba(163, 174, 208, 0.25)",
                        line_width=1,
                    )
            except Exception:
                pass

    # A5. Annotation — current usage value (top-left)
    if y_pct:
        current_val = y_pct[-1]
        color_val = "#05CD99" if current_val < 60 else "#FFB547" if current_val < 80 else "#EE5D50"
        fig.add_annotation(
            text=f"<b>{current_val:.1f}%</b> current",
            x=0.01, y=0.97,
            xref="paper", yref="paper",
            showarrow=False,
            font=dict(size=13, color=color_val, family="DM Sans"),
            bgcolor="rgba(255,255,255,0.85)",
            bordercolor=color_val,
            borderwidth=1,
            borderpad=6,
            align="left",
        )

    show, leg = _resolve_legend(show_legend)
    layout_updates = dict(
        title=dict(
            text=f"<b>{title}</b>",
            font=dict(size=13, color="#2B3674", family="DM Sans", weight=700),
            x=0,
            xanchor="left",
            pad=dict(b=8),
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=show,
        margin=dict(l=40, r=60, t=44, b=36),
        height=height,
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor="rgba(255,255,255,0.97)",
            bordercolor="rgba(67, 24, 255, 0.15)",
            font=dict(family="DM Sans", size=12, color="#2B3674"),
        ),
        xaxis=dict(
            showgrid=False,
            zeroline=False,
            showticklabels=True,
            tickfont=dict(size=11, color="#A3AED0", family="DM Sans"),
            tickformat="%b %d",
            tickangle=0,
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor="rgba(227, 234, 252, 0.4)",
            gridwidth=1,
            zeroline=False,
            showticklabels=True,
            ticksuffix="%",
            tickfont=dict(size=11, color="#A3AED0", family="DM Sans"),
            range=[y_min, y_max],
            side="right",
            nticks=5,
        ),
        font=dict(family="DM Sans", color="#A3AED0"),
    )
    if show and leg:
        layout_updates["legend"] = leg
    fig.update_layout(**layout_updates)
    return fig


def create_gauge_chart(value, max_value, title, color="#4318FF", height=200):
    """Gauge (indicator) for usage: value / max_value as percentage."""
    try:
        val = float(value)
        mx = float(max_value) if max_value else 100
    except (TypeError, ValueError):
        val, mx = 0, 100
    pct = (val / mx * 100) if mx > 0 else 0
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=pct,
        number={"suffix": "%", "font": dict(size=40, color="#2B3674", family="DM Sans", weight=990)},
        gauge={
            "axis": {"range": [0, 100], "nticks": 5, "tickfont": {"size": 8, "color": "#A3AED0", "family": "DM Sans"}, "ticklen": 3, "tickwidth": 1},
            "bar": {"color": color},
            "steps": [
                {"range": [0, 50], "color": "#F4F7FE"},
                {"range": [50, 80], "color": "rgba(67, 24, 255, 0.15)"},
                {"range": [80, 100], "color": "rgba(238, 93, 80, 0.15)"},
            ],
            "threshold": {"line": {"color": "#2B3674", "width": 4}, "value": 90},
        },
        title={"text": title.upper(), "font": dict(size=13, color="#A3AED0", family="DM Sans")},
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=20, r=20, t=40, b=20),
        height=height,
        font=dict(family="DM Sans", color="#A3AED0"),
    )
    return fig


def create_premium_gauge_chart(pct_value, title, color="#4318FF", height=220, show_threshold=True):
    """Premium semi-circle gauge chart using percentage value directly."""
    try:
        pct = float(pct_value)
    except (TypeError, ValueError):
        pct = 0.0
    step_mid = f"rgba({int(color[1:3], 16)}, {int(color[3:5], 16)}, {int(color[5:7], 16)}, 0.3)" if color.startswith("#") and len(color) == 7 else "rgba(67,24,255,0.3)"
    gauge_cfg = {
        "axis": {"range": [0, 100], "nticks": 5, "tickfont": {"size": 8, "color": "#A3AED0", "family": "DM Sans"}, "ticklen": 3, "tickwidth": 1},
        "bar": {"color": color},
        "steps": [
            {"range": [0, 50], "color": "#E9EDF7"},
            {"range": [50, 80], "color": step_mid},
            {"range": [80, 100], "color": "rgba(238, 93, 80, 0.3)"},
        ],
    }
    if show_threshold:
        gauge_cfg["threshold"] = {"line": {"color": "#2B3674", "width": 4}, "value": 90}
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=pct,
        number={"suffix": "%", "font": {"size": 36, "color": "#2B3674", "family": "DM Sans", "weight": 900}},
        gauge=gauge_cfg,
        title={"text": title, "font": {"size": 13, "color": "#A3AED0", "family": "DM Sans"}},
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=20, r=20, t=44, b=20),
        height=height,
        font=dict(family="DM Sans", color="#A3AED0"),
    )
    return fig


def create_premium_gauge_with_avg(avg_pct, max_pct, title, color="#4318FF", height=220):
    """Premium semi-circle gauge showing peak value with avg annotation below."""
    try:
        avg = float(avg_pct)
        mx = float(max_pct)
    except (TypeError, ValueError):
        avg, mx = 0.0, 0.0
    step_mid = f"rgba({int(color[1:3], 16)}, {int(color[3:5], 16)}, {int(color[5:7], 16)}, 0.3)" if color.startswith("#") and len(color) == 7 else "rgba(67,24,255,0.3)"
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=mx,
        number={"suffix": "%", "font": {"size": 32, "color": "#2B3674", "family": "DM Sans", "weight": 900}},
        gauge={
            "axis": {"range": [0, 100], "nticks": 5, "tickfont": {"size": 8, "color": "#A3AED0", "family": "DM Sans"}, "ticklen": 3, "tickwidth": 1},
            "bar": {"color": color},
            "steps": [
                {"range": [0, 50], "color": "#E9EDF7"},
                {"range": [50, 80], "color": step_mid},
                {"range": [80, 100], "color": "rgba(238, 93, 80, 0.3)"},
            ],
            "threshold": {"line": {"color": "#2B3674", "width": 4}, "value": 90},
        },
        title={"text": f"{title}<br><span style='font-size:11px;color:#A3AED0'>avg {int(avg)}%</span>", "font": {"size": 13, "color": "#A3AED0", "family": "DM Sans"}},
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=20, r=20, t=44, b=20),
        height=height,
        font=dict(family="DM Sans", color="#A3AED0"),
    )
    return fig


def create_energy_semi_circle(labels, values, height=280):
    """
    Energy by Source — Yarım Halka (Semi-Circle Donut).
    Düz taban altta; toplam kW merkez alt noktada büyük tipografiyle.
    """
    try:
        total = sum(float(v) for v in values if v is not None)
    except (TypeError, ValueError):
        total = 0.0

    # Dummy dilim: diğer tüm dilimlerin toplamı kadar, tamamen şeffaf
    dummy_val = total if total > 0 else 1

    full_labels = list(labels) + [""]
    full_values = list(values) + [dummy_val]
    full_colors = ["#4318FF", "#05CD99", "#FFB547", "rgba(0,0,0,0)"]

    # Renk sayısını veri sayısına göre kırp
    color_slice = full_colors[: len(labels)] + ["rgba(0,0,0,0)"]

    fig = go.Figure(data=[go.Pie(
        labels=full_labels,
        values=full_values,
        hole=0.60,
        rotation=180,
        direction="clockwise",
        sort=False,
        marker=dict(
            colors=color_slice,
            line=dict(color="rgba(0,0,0,0)", width=0),
        ),
        textinfo="none",
        hovertemplate="<b>%{label}</b><br>%{value:,.0f} kW<extra></extra>",
    )])

    center_text = (
        f"<span style='font-size:26px;font-weight:900;color:#2B3674'>"
        f"{total:,.0f}"
        f"</span>"
        f"<br>"
        f"<span style='font-size:11px;color:#A3AED0'>kW Total</span>"
    )

    fig.update_layout(
        annotations=[dict(
            text=center_text,
            x=0.5,
            y=0.10,
            xanchor="center",
            yanchor="middle",
            showarrow=False,
            align="center",
        )],
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.04,
            xanchor="center",
            x=0.5,
            font=dict(family="DM Sans", size=12, color="#2B3674"),
            bgcolor="rgba(0,0,0,0)",
            itemsizing="constant",
            traceorder="normal",
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=10, b=50),
        height=height,
        font=dict(family="DM Sans", color="#A3AED0"),
    )

    return fig


def create_dc_treemap(dc_names, dc_vms, height=320):
    """
    DC Comparison — Treemap.
    Kutu büyüklüğü VM sayısını temsil eder.
    Büyük DC (yüksek VM) geniş kutu, küçük DC dar kutu.
    Renk: VM sayısına göre mor → turkuaz gradyan.
    """
    safe_vms = [max(1, int(v or 0)) for v in dc_vms]

    fig = go.Figure(go.Treemap(
        labels=dc_names,
        values=safe_vms,
        parents=[""] * len(dc_names),
        branchvalues="total",
        marker=dict(
            colorscale=[
                [0.0,  "#7B2FFF"],
                [0.35, "#4318FF"],
                [0.70, "#2196F3"],
                [1.0,  "#05CD99"],
            ],
            colors=safe_vms,
            showscale=False,
            line=dict(
                color="rgba(255,255,255,0.15)",
                width=2,
            ),
            pad=dict(t=4, l=4, r=4, b=4),
        ),
        textfont=dict(
            family="DM Sans",
            color="rgba(255,255,255,0.92)",
        ),
        textposition="middle center",
        texttemplate=(
            "<b>%{label}</b><br>"
            "<span style='font-size:11px;opacity:0.85'>%{value:,} VMs</span>"
        ),
        hovertemplate=(
            "<b>%{label}</b><br>"
            "VM Count: %{value:,}<br>"
            "%{percentRoot:.1%} of total"
            "<extra></extra>"
        ),
        tiling=dict(
            packing="squarify",
        ),
    ))

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=0, b=0),
        height=height,
        font=dict(family="DM Sans", color="rgba(255,255,255,0.9)"),
    )

    return fig


def create_energy_breakdown_chart(labels, values, title="Energy by source", height=260):
    """Premium ring chart — total kW centered, legend right outside, no inline labels."""
    try:
        total = sum(float(v) for v in values if v is not None)
    except (TypeError, ValueError):
        total = 0.0

    center_text = (
        f"<span style='font-size:28px;font-weight:900;color:#2B3674'>"
        f"{total:,.0f}"
        f"</span>"
        f"<br>"
        f"<span style='font-size:11px;color:#A3AED0'>kW Total</span>"
    )

    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        hole=0.68,
        marker=dict(
            colors=["#4318FF", "#05CD99"],
            line=dict(color="rgba(0,0,0,0)", width=0),
        ),
        textinfo="none",
        hovertemplate="<b>%{label}</b><br>%{value:,.0f} kW — %{percent}<extra></extra>",
        direction="clockwise",
        sort=False,
    )])

    fig.update_layout(
        annotations=[dict(
            text=center_text,
            x=0.5,
            y=0.5,
            xanchor="center",
            yanchor="middle",
            showarrow=False,
            align="center",
        )],
        showlegend=True,
        legend=dict(
            orientation="v",
            x=1.05,
            y=0.5,
            xanchor="left",
            yanchor="middle",
            font=dict(family="DM Sans", size=12, color="#2B3674"),
            bgcolor="rgba(0,0,0,0)",
            itemsizing="constant",
            tracegroupgap=10,
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=120, t=16, b=16),
        height=height,
        font=dict(family="DM Sans", color="#A3AED0"),
    )
    return fig


# Elite icon map — enerji kaynaklarına göre sembol
_ENERGY_ICONS = {
    "IBM Power": "⚡",
    "vCenter":   "☁️",
    "Rack":      "🏗️",
    "Solar":     "☀️",
    "Wind":      "💨",
}


def create_energy_elite(labels, values, height=300):
    """
    Elite Energy Gauge — Tesla tarzı fütüristik yarım halka.

    Özellikler:
    - Semi-circle (rotation=180, dummy slice)
    - 42px ultra-bold merkez rakam
    - Segmented beyaz çizgiler (parçalı donanım hissi)
    - Emoji pill legend
    - customdata ile hover altyapısı
    """
    try:
        total = sum(float(v) for v in values if v is not None)
    except (TypeError, ValueError):
        total = 0.0

    dummy_val = total if total > 0 else 1.0

    # Legend için emoji prefix
    icon_labels = [
        f"{_ENERGY_ICONS.get(lbl, '●')} {lbl}"
        for lbl in labels
    ]
    full_labels = icon_labels + [""]       # "" → dummy (legend'da görünmez)
    full_values = list(values) + [dummy_val]

    # Renk paleti — son eleman dummy için şeffaf
    palette = ["#4318FF", "#05CD99", "#FFB547", "#A78BFA"]
    color_slice = palette[: len(labels)] + ["rgba(0,0,0,0)"]

    # customdata — dilim yüzdesi ve kW değeri (hover için)
    total_safe = total if total > 0 else 1
    pcts = [round(100 * float(v) / total_safe, 1) for v in values] + [0]

    fig = go.Figure(data=[go.Pie(
        labels=full_labels,
        values=full_values,
        hole=0.62,
        rotation=180,
        direction="clockwise",
        sort=False,
        marker=dict(
            colors=color_slice,
            line=dict(
                color="rgba(255,255,255,1)",
                width=3,
            ),
        ),
        textinfo="none",
        hovertemplate=(
            "<b>%{label}</b><br>"
            "%{value:,.0f} kW<br>"
            "%{customdata:.1f}%"
            "<extra></extra>"
        ),
        customdata=pcts,
        pull=[0] * (len(labels) + 1),
    )])

    # Annotation 1: Büyük rakam (42px, ultra-bold, lacivert)
    number_text = (
        f"<span style='"
        f"font-size:42px;"
        f"font-weight:900;"
        f"color:#1a1b41;"
        f"line-height:1;"
        f"font-family:DM Sans,sans-serif;"
        f"'>{total:,.0f}</span>"
    )

    # Annotation 2: "kW TOTAL" label (12px, gri, letter-spaced)
    unit_text = (
        "<span style='"
        "font-size:12px;"
        "font-weight:600;"
        "color:#A3AED0;"
        "letter-spacing:0.12em;"
        "text-transform:uppercase;"
        "font-family:DM Sans,sans-serif;"
        "'>kW TOTAL</span>"
    )

    fig.update_layout(
        annotations=[
            dict(
                text=number_text,
                x=0.5,
                y=0.14,
                xanchor="center",
                yanchor="middle",
                showarrow=False,
                align="center",
            ),
            dict(
                text=unit_text,
                x=0.5,
                y=0.02,
                xanchor="center",
                yanchor="middle",
                showarrow=False,
                align="center",
            ),
        ],
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.06,
            xanchor="center",
            x=0.5,
            font=dict(
                family="DM Sans",
                size=12,
                color="#2B3674",
            ),
            bgcolor="rgba(0,0,0,0)",
            itemsizing="constant",
            traceorder="normal",
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=10, b=60),
        height=height,
        font=dict(family="DM Sans", color="#A3AED0"),
    )

    return fig


def create_energy_elite_v2(labels, values, height=300):
    """
    Elite Energy Gauge v2 — Full Donut, Zero-Overlap Typography.

    Task 6 değişiklikleri:
    - Semi-circle (dummy + rotation) KALDIRILDI → Tam Donut
    - Annotation: y=0.55 rakam / y=0.45 etiket → asla üst üste gelmiyor
    - Neon glow: wrapper div'de (bu fonksiyon değil, home.py'de)
    - Segmented gaps: marker.line korunuyor
    - Emoji legend: korunuyor
    """
    try:
        total = sum(float(v) for v in values if v is not None)
    except (TypeError, ValueError):
        total = 0.0

    # Emoji prefix legend
    icon_labels = [
        f"{_ENERGY_ICONS.get(lbl, '●')} {lbl}"
        for lbl in labels
    ]

    # Renk paleti
    palette = ["#4318FF", "#05CD99", "#FFB547", "#A78BFA"]
    color_slice = palette[: len(labels)]

    # customdata — hover için yüzde
    total_safe = total if total > 0 else 1
    pcts = [round(100 * float(v) / total_safe, 1) for v in values]

    fig = go.Figure(data=[go.Pie(
        labels=icon_labels,
        values=list(values),
        hole=0.65,
        sort=False,
        marker=dict(
            colors=color_slice,
            line=dict(
                color="rgba(255,255,255,1)",
                width=3,
            ),
        ),
        textinfo="none",
        hovertemplate=(
            "<b>%{label}</b><br>"
            "%{value:,.0f} kW<br>"
            "%{customdata:.1f}%"
            "<extra></extra>"
        ),
        customdata=pcts,
        direction="clockwise",
    )])

    # Annotation 1: Büyük rakam — y=0.55 (ortanın 5 birim üstü)
    number_text = (
        f"<span style='"
        f"font-size:42px;"
        f"font-weight:900;"
        f"color:#1a1b41;"
        f"line-height:1;"
        f"font-family:DM Sans,sans-serif;"
        f"'>{total:,.0f}</span>"
    )

    # Annotation 2: "kW TOTAL" etiket — y=0.45 (ortanın 5 birim altı)
    unit_text = (
        "<span style='"
        "font-size:12px;"
        "font-weight:600;"
        "color:#A3AED0;"
        "letter-spacing:0.12em;"
        "text-transform:uppercase;"
        "font-family:DM Sans,sans-serif;"
        "'>kW TOTAL</span>"
    )

    fig.update_layout(
        annotations=[
            dict(
                text=number_text,
                x=0.5,
                y=0.55,
                xanchor="center",
                yanchor="middle",
                showarrow=False,
                align="center",
            ),
            dict(
                text=unit_text,
                x=0.5,
                y=0.45,
                xanchor="center",
                yanchor="middle",
                showarrow=False,
                align="center",
            ),
        ],
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.06,
            xanchor="center",
            x=0.5,
            font=dict(family="DM Sans", size=12, color="#2B3674"),
            bgcolor="rgba(0,0,0,0)",
            itemsizing="constant",
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=16, b=60),
        height=height,
        font=dict(family="DM Sans", color="#A3AED0"),
    )

    return fig


def create_dual_line_chart(timestamps, in_vals, out_vals, title: str, height: int = 260, show_legend=True):
    """
    Dual line chart for SAN traffic trend.
    - In rate (blue) with subtle area fill
    - Out rate (green) as a solid line
    """
    try:
        x = list(timestamps or [])
        y_in = [float(v or 0) for v in (in_vals or [])]
        y_out = [float(v or 0) for v in (out_vals or [])]
    except Exception:
        x, y_in, y_out = [], [], []

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x,
            y=y_in,
            mode="lines",
            name="In",
            line=dict(width=3, color="#4318FF"),
            fill="tozeroy",
            fillcolor="rgba(67, 24, 255, 0.10)",
            hovertemplate="<b>In</b><br>%{x}<br>%{y:,.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=y_out,
            mode="lines",
            name="Out",
            line=dict(width=3, color="#05CD99"),
            hovertemplate="<b>Out</b><br>%{x}<br>%{y:,.0f}<extra></extra>",
        )
    )

    show, leg = _resolve_legend(show_legend)
    layout_updates = dict(
        title=dict(text=title, font=dict(size=14, color="#2B3674", family="DM Sans", weight=700)),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=show,
        margin=dict(l=20, r=20, t=40, b=36 if show else 20),
        height=height,
        hovermode="x unified",
        xaxis=dict(showgrid=False, zeroline=False),
        yaxis=dict(showgrid=False, zeroline=False),
        font=dict(family="DM Sans", color="#A3AED0"),
    )
    if show and leg:
        layout_updates["legend"] = leg
    fig.update_layout(**layout_updates)
    return fig


def create_sparkline_chart(values, label: str, unit: str, color: str, height: int = 100, show_legend=False):
    """Minimal sparkline (used inside IBM Power storage KPI cards)."""
    try:
        y = [float(v or 0) for v in (values or [])]
    except Exception:
        y = []

    x = list(range(len(y)))
    fig = go.Figure()
    show, leg = _resolve_legend(show_legend)
    fig.add_trace(
        go.Scatter(
            x=x,
            y=y,
            mode="lines",
            name=label,
            line=dict(width=3, color=color),
            fill="tozeroy",
            fillcolor="rgba(67, 24, 255, 0.08)" if color == "#4318FF" else "rgba(5, 205, 153, 0.06)",
            hovertemplate=f"<b>{label}</b><br>%{{y:,.2f}} {unit}<extra></extra>",
        )
    )

    layout_updates = dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=0, b=16 if show else 0),
        height=height,
        showlegend=show,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
    )
    if show and leg:
        layout_updates["legend"] = leg
    fig.update_layout(**layout_updates)
    return fig
