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