import plotly.graph_objects as go

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

    fig.update_layout(
        annotations=[dict(
            text=f"<b>{int(val)}%</b>",
            x=0.5,
            y=0.5,
            xanchor="center",
            yanchor="middle",
            font=dict(size=28, color="#2B3674", family="DM Sans"),
            showarrow=False,
        )],
        title=dict(
            text=f"<b>{label}</b>",
            x=0.5,
            xanchor="center",
            font=dict(size=12, color="#A3AED0", family="DM Sans"),
        ),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.08,
            xanchor="center",
            x=0.5,
            font=dict(size=10, color="#A3AED0", family="DM Sans"),
            bgcolor="rgba(0,0,0,0)",
        ),
        margin=dict(l=8, r=8, t=44, b=28),
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
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.1,
            xanchor="center",
            x=0.5,
            font=dict(size=10, color="#A3AED0", family="DM Sans"),
            bgcolor="rgba(0,0,0,0)",
        ),
        margin=dict(l=8, r=8, t=44, b=32),
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

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x,
            y=y_pct,
            mode="lines",
            fill="tozeroy",
            line=dict(width=3, color="#4318FF"),
            fillcolor="rgba(67, 24, 255, 0.12)",
            hovertemplate="<b>%{x}</b><br>%{y:.1f}% utilized<extra></extra>",
            name="Utilization %",
        )
    )

    show, leg = _resolve_legend(show_legend)
    layout_updates = dict(
        title=dict(text=title, font=dict(size=14, color="#2B3674", family="DM Sans", weight=700)),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=show,
        margin=dict(l=20, r=20, t=40, b=28 if show else 10),
        height=height,
        hovermode="x unified",
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=True),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
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
        number={"suffix": "%"},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": color},
            "steps": [{"range": [0, 50], "color": "#E9EDF7"}, {"range": [50, 80], "color": "rgba(67, 24, 255, 0.3)"}, {"range": [80, 100], "color": "rgba(238, 93, 80, 0.3)"}],
            "threshold": {"line": {"color": "#2B3674", "width": 4}, "value": 90},
        },
        title={"text": title},
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=20, r=20, t=40, b=20),
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
