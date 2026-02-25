import plotly.graph_objects as go

def create_gradient_area_chart(df, x_col, y_col, title):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df[x_col], y=df[y_col], mode='lines', fill='tozeroy',
        line=dict(width=3, color='#4318FF'),
        fillcolor='rgba(67, 24, 255, 0.1)',
    ))
    fig.update_layout(
        title=dict(text=title, font=dict(size=14, color='#2B3674', family="DM Sans")),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        showlegend=False,
        margin=dict(l=0, r=0, t=30, b=0),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=True),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        hovermode="x unified"
    )
    return fig

def create_bar_chart(data, x_col, y_col, title, color="#4318FF", height=250):
    fig = go.Figure()
    # Data bir dict gelirse listeye çevir, DataFrame gelirse sütunu al
    x_data = data[x_col] if isinstance(data, dict) else data[x_col].tolist()
    y_data = data[y_col] if isinstance(data, dict) else data[y_col].tolist()

    fig.add_trace(go.Bar(
        x=x_data, y=y_data,
        marker_color=color,
        name=title
    ))
    
    fig.update_layout(
        title=dict(text=title, font=dict(family="DM Sans, sans-serif", size=16, color="#2B3674", weight=700)),
        margin=dict(l=20, r=20, t=40, b=20),
        height=height,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        showlegend=False,
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=True),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=True),
        font=dict(family="DM Sans, sans-serif", color="#A3AED0")
    )
    return fig

def create_usage_donut_chart(value, label, color="#4318FF"):
    try:
        val = float(value)
    except:
        val = 0
    remaining = 100 - val
    
    fig = go.Figure(data=[go.Pie(
        values=[val, remaining],
        labels=["Used", "Free"],
        hole=0.7,
        marker=dict(colors=[color, "#E9EDF7"]),
        sort=False,
        textinfo='none',
        hoverinfo='label+value'
    )])

    fig.update_layout(
        annotations=[dict(
            text=f"{int(val)}%",
            x=0.5, y=0.5,
            font=dict(size=24, color="#2B3674", family="DM Sans", weight="bold"),
            showarrow=False
        )],
        title=dict(text=label, x=0.5, xanchor='center', font=dict(size=14, color="#A3AED0", family="DM Sans")),
        showlegend=False,
        margin=dict(l=20, r=20, t=40, b=20),
        height=200,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)'
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


def create_grouped_bar_chart(labels, series_dict, title, height=300):
    """Grouped bar chart: labels on x, multiple series side by side."""
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
        barmode="group",
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


def create_energy_breakdown_chart(labels, values, title="Energy by source", height=250):
    """Pie or bar for energy breakdown (e.g. Racks, IBM, vCenter)."""
    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        hole=0.5,
        marker=dict(colors=["#4318FF", "#05CD99", "#FFB547"]),
        textinfo="label+percent",
        hoverinfo="label+value+percent",
    )])
    fig.update_layout(
        title=dict(text=title, font=dict(size=14, color="#2B3674", family="DM Sans")),
        showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=20, r=20, t=40, b=20),
        height=height,
        font=dict(family="DM Sans", color="#A3AED0"),
    )
    return fig
