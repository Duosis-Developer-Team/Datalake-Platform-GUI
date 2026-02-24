🎨 Legacy UI & Frontend Components Reference
Bu dosya, eski monolitik yapıda kullanılan tüm görsel bileşenleri, sayfa düzenlerini (layouts) ve CSS stillerini içerir. Senior Dev (Claude), bu mantığı gui-service içerisine Plotly Dash ve Dash Mantine Components (DMC) kullanarak asenkron bir yapıda taşımalıdır.

## 1. Global Layout & Sidebar
Kaynak: src/components/sidebar.py ve src/app.py
Eski yapıda menü navigasyonu ve ana çerçeve (layout) nasıl kurulmuştu?

Python
[
import dash_mantine_components as dmc
from dash_iconify import DashIconify
from dash import html

def create_sidebar(active_path):
    # Sidebar Marka Alanı
    brand = html.Div(
        [
            DashIconify(icon="solar:widget-5-bold-duotone", width=30, color="#4318FF"),
            html.Span("BULUTİSTAN", style={"fontSize": "24px", "fontWeight": "700", "color": "#2B3674", "marginLeft": "10px"})
        ],
        style={"display": "flex", "alignItems": "center", "marginBottom": "40px", "paddingLeft": "16px"}
    )

    # Linkler
    # Düzeltme: DMC 0.14'te 'icon' yerine 'leftSection' kullanılır.
    links = [
        dmc.NavLink(
            label="Dashboard",
            leftSection=DashIconify(icon="solar:home-smile-bold-duotone", width=20),
            href="/",
            className="sidebar-link",
            active=active_path == "/" or active_path == "",
            variant="subtle",
            color="indigo",
            style={"borderRadius": "8px", "fontWeight": "500", "marginBottom": "5px"}
        ),
        dmc.NavLink(
            label="Data Centers",
            leftSection=DashIconify(icon="solar:server-square-bold-duotone", width=20),
            href="/datacenters",
            className="sidebar-link",
            active=active_path.startswith("/datacenter") or active_path == "/datacenters",
            variant="subtle",
            color="indigo",
            style={"borderRadius": "8px", "fontWeight": "500", "marginBottom": "5px"}
        ),
        # Pasif Linkler (Görsellik İçin)
        dmc.NavLink(
            label="Analytics",
            leftSection=DashIconify(icon="solar:chart-square-bold-duotone", width=20),
            href="#",
            className="sidebar-link",
            disabled=True,
        ),
        dmc.NavLink(
            label="Settings",
            leftSection=DashIconify(icon="solar:settings-bold-duotone", width=20),
            href="#",
            className="sidebar-link",
            disabled=True,
        ),
    ]

    return html.Div(
        [
            brand,
            dmc.Stack(links, gap=4)
        ],
        style={
            "height": "100%",
            "width": "100%",
            "padding": "24px",
            "backgroundColor": "#FFFFFF",
        }
    )
]

[
import dash
from dash import Dash, html, dcc, page_container, _dash_renderer
import dash_mantine_components as dmc
from dotenv import load_dotenv

# 0. Load .env before any service import so DB credentials are available
load_dotenv()

from src.components.sidebar import create_sidebar
from src.services.shared import service
from src.services.scheduler_service import start_scheduler

# 1. React 18 requirement for DMC
_dash_renderer._set_react_version("18.2.0")

# 2. STİL DOSYALARI (DMC 0.14 için ZORUNLU)
# Eski sürümde 'withNormalizeCSS' vardı, şimdi bu linkleri ekliyoruz.
stylesheets = [
    "https://unpkg.com/@mantine/core@7.10.0/styles.css",
    "https://unpkg.com/@mantine/dates@7.10.0/styles.css",
    "https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&display=swap" # Senin fontun
]

app = Dash(
    __name__, 
    use_pages=True, 
    pages_folder="src/pages", # <-- Klasör hatasını çözen satır
    external_stylesheets=stylesheets, # <-- Stil hatasını çözen satır
    suppress_callback_exceptions=True,
    title="Bulutistan Dashboard"
)
server = app.server

# 3. Global Layout
app.layout = dmc.MantineProvider(
    # HATA ÇIKARAN 'withNormalizeCSS' ve 'withGlobalStyles' SİLİNDİ.
    theme={
        "fontFamily": "'DM Sans', sans-serif",
        "headings": {
            "fontFamily": "'DM Sans', sans-serif"
        },
        "primaryColor": "indigo",
    },
    children=[
        dcc.Location(id="url", refresh=False),
        html.Div(
            [
                # Sol Sidebar Konteyneri
                html.Div(
                    id="sidebar-container",
                    style={
                        "width": "260px",
                        "position": "fixed",
                        "top": 0,
                        "left": 0,
                        "height": "100vh",
                        "zIndex": 999
                    }
                ),
                
                # Sağ İçerik Alanı
                html.Div(
                    page_container,
                    style={
                        "marginLeft": "260px",
                        "padding": "30px",
                        "minHeight": "100vh",
                        "width": "calc(100% - 260px)",
                        "backgroundColor": "#F4F7FE"
                    }
                )
            ],
            style={"display": "flex", "backgroundColor": "#F4F7FE", "minHeight": "100vh"}
        )
    ]
)

# Sidebar Callback'i
@app.callback(
    dash.Output("sidebar-container", "children"),
    dash.Input("url", "pathname")
)
def update_sidebar(pathname):
    return create_sidebar(pathname or "/")

# 4. Start background cache scheduler (warm cache now + refresh every 15 min)
# Runs outside __main__ guard so it also starts under Gunicorn / production.
_scheduler = start_scheduler(service)

if __name__ == "__main__":
    app.run(debug=True, port=8050)
]

## 2. Visualization & Charts Logic
Kaynak: src/components/charts.py
Grafiklerin (Plotly/Dash) oluşturulma mantığı, renk skalaları ve veri eşleme (mapping) detayları.

Python
[
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
]

## 3. Pages & Routing
Kaynak: src/pages/ klasörü (home.py, cluster_view.py, datacenters.py vb.)
Hangi sayfa hangi veriyi bekliyor ve kullanıcı etkileşimleri (callbacks) nasıl çalışıyor?

Python
[
import dash
from dash import html, dcc
import dash_mantine_components as dmc
import pandas as pd
import random
from dash_iconify import DashIconify
from src.services.shared import service
from src.components.charts import create_gradient_area_chart

dash.register_page(__name__, path='/')

# Fake Data Trend for Chart (preserving visual appeal as DB has no traffic data yet)
def get_traffic_data():
    hours = [f"{i}:00" for i in range(24)]
    traffic = [random.randint(500, 2000) for _ in range(24)]
    return pd.DataFrame({"time": hours, "requests": traffic})

def metric_card(title, value, icon_name, subtext=None, color="#4318FF"):
    return html.Div(
        className="nexus-card",
        children=[
            dmc.Group(
                align="center",
                gap="sm",
                style={"marginBottom": "10px"},
                children=[
                    dmc.ThemeIcon(
                        size="lg",
                        radius="md",
                        variant="light",
                        color=color if color != "#4318FF" else "indigo",
                        children=DashIconify(icon=icon_name, width=22)
                    ),
                    html.H3(title, style={"margin": 0, "color": "#A3AED0", "fontSize": "0.9rem", "fontWeight": "500"})
                ]
            ),
            html.H2(value, style={"margin": "0", "color": "#2B3674", "fontSize": "2rem", "fontWeight": "700"}),
            html.P(subtext, style={"margin": "5px 0 0 0", "color": "#05CD99", "fontSize": "0.8rem", "fontWeight": "600"}) if subtext else None
        ]
    )

def layout():
    # Fetch Real Global Data
    summary = service.get_global_overview()
    df_traffic = get_traffic_data()

    return html.Div([
        # Header (Nexus Glass Effect)
        html.Div(
            className="nexus-glass",
            children=[
                html.H1("Dashboard Overview", style={"margin": 0, "color": "#2B3674", "fontSize": "1.5rem"}),
                html.P("Real-time system performance metrics", style={"margin": "5px 0 0 0", "color": "#A3AED0"})
            ],
            style={"padding": "20px 30px", "marginBottom": "30px", "borderRadius": "0 0 20px 20px"}
        ),
        
        # Metrics Grid
        dmc.SimpleGrid(
            cols=3,
            spacing="lg",
            children=[
                metric_card("Total Hosts", str(summary['total_hosts']), "material-symbols:dns-outline", "Global Infrastructure"),
                metric_card("Total VMs", str(summary['total_vms']), "material-symbols:laptop-mac-outline", "Virtual Machines", color="teal"),
                metric_card("Total Energy", f"{summary['total_energy_kw']:,} kW", "material-symbols:bolt-outline", "Real-time Power", color="orange"),
            ],
            style={"marginBottom": "30px", "padding": "0 30px"}
        ),

        # Main Chart Area
        html.Div(
            className="nexus-card",
            style={"margin": "0 30px"},
            children=[
                 html.Div([
                    html.H3("Network Traffic Trends", style={"margin": 0, "color": "#2B3674"}),
                ], style={"marginBottom": "20px"}),
                dcc.Graph(
                    figure=create_gradient_area_chart(df_traffic, "time", "requests", "Global Data Traffic"),
                    config={'displayModeBar': False},
                    style={"height": "350px"}
                )
            ]
        )
    ])
]

[
import dash
from dash import html, dcc
import dash_mantine_components as dmc
from dash_iconify import DashIconify
from src.services.shared import service

dash.register_page(__name__, path_template='/cluster/<cluster_id>')

def layout(cluster_id=None):
    # Cluster view logic is currently placeholder as we transition from mock data.
    # The current DB schema aggregates at DC level, so cluster-specific drill-down 
    # specific to 'cluster_id' needs to be implemented in a future phase.
    # preventing crash by showing a maintenance/construction message.
    
    return html.Div([
        # Header
        html.Div(
            className="nexus-glass",
            children=[
                dcc.Link(
                    DashIconify(icon="solar:arrow-left-linear", width=24, color="#2B3674"),
                    href="/datacenters", # Fallback to DC list for now
                    style={"marginRight": "16px"}
                ),
                html.Div([
                    html.H1(f"Cluster: {cluster_id}", style={"margin": "0", "color": "#2B3674", "fontSize": "1.5rem"}),
                    html.P("Detailed cluster view is under construction.", style={"margin": "0 0 0 12px", "color": "#A3AED0", "fontSize": "0.9rem"})
                ], style={"display": "flex", "alignItems": "baseline"}),
            ],
            style={"padding": "20px 30px", "marginBottom": "30px", "display": "flex", "alignItems": "center"}
        ),

        # Placeholder Card
        html.Div(
            className="nexus-card",
            style={"margin": "0 30px", "textAlign": "center", "padding": "50px"},
            children=[
                DashIconify(icon="solar:construction-bold-duotone", width=64, color="#FFB547"),
                html.H2("Work in Progress", style={"marginTop": "20px", "color": "#2B3674"}),
                html.P("We are currently connecting this view to the live database metrics.", style={"color": "#A3AED0"}),
                dcc.Link(dmc.Button("Back to Data Centers", variant="light", color="indigo", mt="md"), href="/datacenters")
            ]
        )
    ])

]

## 4. Custom Styling (CSS)
Kaynak: assets/style.css
Eski temadaki renk kodları, fontlar ve özel margin/padding ayarları.

CSS
[
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&display=swap');

/* --- 1. CORE LAYOUT --- */
body {
    background-color: #F4F7FE;
    /* Nexus Light Blue */
    color: #2B3674;
    /* Navy Blue Text */
    font-family: 'DM Sans', sans-serif;
    margin: 0;
    overflow-x: hidden;
}

/* Premium Scrollbar */
::-webkit-scrollbar {
    width: 6px;
}

::-webkit-scrollbar-track {
    background: transparent;
}

::-webkit-scrollbar-thumb {
    background: #cdd5e0;
    border-radius: 20px;
}

::-webkit-scrollbar-thumb:hover {
    background: #4318FF;
}

/* --- 2. NEXUS CARD (The Secret Sauce) --- */
.nexus-card {
    background-color: #FFFFFF !important;
    border: none !important;
    border-radius: 20px !important;
    /* DOUBLE SHADOW for Depth */
    box-shadow:
        0px 18px 40px rgba(112, 144, 176, 0.12),
        0px 5px 10px rgba(112, 144, 176, 0.05) !important;
    padding: 24px !important;
    transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
    position: relative;
    overflow: hidden;
}

.nexus-card:hover {
    transform: translateY(-5px);
    box-shadow:
        0px 30px 60px rgba(112, 144, 176, 0.20),
        0px 10px 20px rgba(112, 144, 176, 0.10) !important;
}

/* --- 3. GLASSMORPHISM HEADER --- */
.nexus-glass {
    background: rgba(255, 255, 255, 0.65) !important;
    backdrop-filter: blur(12px) !important;
    -webkit-backdrop-filter: blur(12px) !important;
    border-bottom: 1px solid rgba(255, 255, 255, 0.5) !important;
    position: sticky;
    top: 0;
    z-index: 1000;
}

/* --- 4. SIDEBAR --- */
.sidebar-link {
    border-radius: 12px !important;
    color: #A3AED0 !important;
    /* Inactive Gray */
    font-weight: 500 !important;
    margin-bottom: 8px !important;
    padding: 12px 16px !important;
    transition: all 0.2s ease;
}

.sidebar-link:hover {
    background-color: rgba(67, 24, 255, 0.05) !important;
    color: #4318FF !important;
    /* Active Purple */
    padding-left: 20px !important;
}

.sidebar-link[data-active="true"] {
    background: linear-gradient(135deg, #4318FF 0%, #5630FF 100%) !important;
    color: #FFFFFF !important;
    font-weight: 700 !important;
    box-shadow: 0px 10px 20px rgba(67, 24, 255, 0.25) !important;
}

/* --- 5. ANIMATED STATUS DOTS --- */
@keyframes pulse-green {
    0% {
        box-shadow: 0 0 0 0 rgba(5, 205, 153, 0.4);
    }

    70% {
        box-shadow: 0 0 0 8px rgba(5, 205, 153, 0);
    }

    100% {
        box-shadow: 0 0 0 0 rgba(5, 205, 153, 0);
    }
}

@keyframes pulse-red {
    0% {
        box-shadow: 0 0 0 0 rgba(238, 93, 80, 0.4);
    }

    70% {
        box-shadow: 0 0 0 8px rgba(238, 93, 80, 0);
    }

    100% {
        box-shadow: 0 0 0 0 rgba(238, 93, 80, 0);
    }
}

.status-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    display: inline-block;
    margin-right: 8px;
}

.status-running {
    background-color: #05CD99;
    animation: pulse-green 2s infinite;
}

.status-stopped {
    background-color: #EE5D50;
    animation: pulse-red 2s infinite;
}

/* --- 6. TYPOGRAPHY & TABLE --- */
.gradient-text {
    background: linear-gradient(90deg, #4318FF 0%, #00DBE3 100%);
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
    font-weight: 800;
    letter-spacing: -0.5px;
}

.nexus-table thead th {
    color: #A3AED0 !important;
    font-weight: 500 !important;
    font-size: 12px !important;
    text-transform: uppercase;
    border-bottom: 1px solid #E9EDF7 !important;
    padding-bottom: 12px !important;
}

.nexus-table tbody td {
    color: #2B3674 !important;
    font-weight: 600 !important;
    padding: 16px 0 !important;
    border-bottom: 1px solid #F4F7FE !important;
}

.nexus-table tr:hover td {
    color: #4318FF !important;
    cursor: pointer;
}
]