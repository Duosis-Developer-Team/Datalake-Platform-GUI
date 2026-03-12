import dash
from dash import html, dcc
import dash_mantine_components as dmc
from dash_iconify import DashIconify
import plotly.graph_objs as go
from src.services import api_client as api
from src.utils.time_range import default_time_range
from src.components.header import create_detail_header


def metric_card(title, value, icon_name, color="#4318FF"):
    return html.Div(
        className="nexus-card",
        style={"padding": "20px"},
        children=[
            dmc.Group(
                align="center",
                gap="sm",
                style={"marginBottom": "8px"},
                children=[
                    dmc.ThemeIcon(
                        size="lg",
                        radius="md",
                        variant="light",
                        color=color if color != "#4318FF" else "indigo",
                        children=DashIconify(icon=icon_name, width=22),
                    ),
                    html.H3(title, style={"margin": 0, "color": "#A3AED0", "fontSize": "0.9rem"}),
                ],
            ),
            html.H2(str(value), style={"margin": "0", "color": "#2B3674", "fontSize": "1.5rem", "fontWeight": "700"}),
        ],
    )


def build_customer_layout(time_range=None, selected_customer=None):
    tr = time_range or default_time_range()
    chosen = "Boyner"
    return html.Div(
        [
            create_detail_header(
                title="Customer View",
                back_href="/",
                back_label="Overview",
                subtitle_badge="👤 Boyner",
                subtitle_color="teal",
                time_range=tr,
                icon="solar:users-group-two-rounded-bold-duotone",
                tabs=None,
            ),
            dmc.SimpleGrid(
                cols=3,
                spacing="lg",
                style={"padding": "0 30px", "marginBottom": "24px"},
                children=[
                    html.Div(
                        className="nexus-card",
                        style={"padding": "24px", "height": "100%"},
                        children=[
                            dmc.Group(
                                justify="space-between",
                                mb="lg",
                                children=[
                                    dmc.Group(
                                        gap="sm",
                                        children=[
                                            dmc.ThemeIcon(
                                                size="xl",
                                                variant="light",
                                                color="indigo",
                                                radius="md",
                                                children=DashIconify(icon="solar:users-group-two-rounded-bold-duotone", width=30),
                                            ),
                                            dmc.Stack(
                                                gap=0,
                                                children=[
                                                    dmc.Text("Boyner", fw=700, size="lg", c="#2B3674"),
                                                    dmc.Text("Customer assets", size="sm", c="#A3AED0", fw=500),
                                                ],
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            dmc.Text(
                                "This card represents the Boyner customer. All metrics below are aggregated totals for this customer across platforms.",
                                size="sm",
                                c="#A3AED0",
                            ),
                        ],
                    )
                ],
            ),
            html.Div(id="customer-view-content", children=_customer_content(chosen, tr)),
        ]
    )


def layout():
    return build_customer_layout(default_time_range())


def _customer_content(customer_name, time_range=None):
    tr = time_range or default_time_range()
    data = api.get_customer_resources(customer_name or "Boyner", tr)
    totals = data.get("totals", {})
    assets = data.get("assets", {})
    intel = assets.get("intel", {})
    power = assets.get("power", {})
    backup = assets.get("backup", {})

    intel_vms = intel.get("vms", {}) or {}
    intel_cpu = intel.get("cpu", {}) or {}
    intel_mem = intel.get("memory_gb", {}) or {}
    intel_disk = intel.get("disk_gb", {}) or {}
    intel_vm_list = intel.get("vm_list", []) or []

    power_lpars = int(power.get("lpar_count", 0) or 0)
    power_cpu = float(power.get("cpu_total", 0.0) or 0.0)
    power_mem = float(power.get("memory_total_gb", 0.0) or 0.0)
    power_vm_list = power.get("vm_list", []) or []

    backup_totals = totals.get("backup", {}) or {}
    veeam_defined = int(backup_totals.get("veeam_defined_sessions", 0) or 0)
    zerto_protected = int(backup_totals.get("zerto_protected_vms", 0) or 0)
    storage_gb = float(backup_totals.get("storage_volume_gb", 0.0) or 0.0)
    netbackup_pre_gib = float(backup_totals.get("netbackup_pre_dedup_gib", 0.0) or 0.0)
    netbackup_post_gib = float(backup_totals.get("netbackup_post_dedup_gib", 0.0) or 0.0)
    zerto_provisioned_gib = float(backup_totals.get("zerto_provisioned_gib", 0.0) or 0.0)

    backup_assets = backup or {}
    veeam_assets = backup_assets.get("veeam", {}) or {}
    zerto_assets = backup_assets.get("zerto", {}) or {}
    storage_assets = backup_assets.get("storage", {}) or {}
    netbackup_assets = backup_assets.get("netbackup", {}) or {}

    veeam_types = veeam_assets.get("session_types", []) or []
    veeam_platforms = veeam_assets.get("platforms", []) or []
    zerto_vpgs = zerto_assets.get("vpgs", []) or []
    netbackup_dedup_factor = netbackup_assets.get("deduplication_factor", "1x")

    return [
        dmc.Tabs(
            color="indigo",
            variant="pills",
            radius="md",
            value="summary",
            children=[
                dmc.TabsList(
                    children=[
                        dmc.TabsTab("Summary", value="summary"),
                        dmc.TabsTab("Intel Virtualization", value="intel"),
                        dmc.TabsTab("HANA Virtualization", value="hana"),
                        dmc.TabsTab("Backup Services", value="backup"),
                    ],
                    style={"padding": "0 30px", "marginBottom": "24px"},
                ),
                dmc.TabsPanel(
                    value="summary",
                    children=dmc.Stack(
                        gap="lg",
                        style={"padding": "0 30px"},
                        children=[
                            dmc.SimpleGrid(
                                cols=3,
                                spacing="lg",
                                children=[
                                    metric_card("Total Customer VMs", totals.get("vms_total", 0), "solar:laptop-bold-duotone", color="teal"),
                                    metric_card("Intel VMs", totals.get("intel_vms_total", 0), "solar:laptop-bold-duotone"),
                                    metric_card("HANA LPARs", totals.get("power_lpar_total", 0), "solar:server-square-bold-duotone", color="orange"),
                                ],
                            ),
                            html.Div(
                                className="nexus-card",
                                style={"padding": "20px"},
                                children=[
                                    html.H3("Compute summary", style={"margin": "0 0 12px 0", "color": "#2B3674"}),
                                    dmc.SimpleGrid(
                                        cols=3,
                                        spacing="lg",
                                        children=[
                                            metric_card("Total CPU (vCPU)", f"{totals.get('cpu_total', 0.0):.1f}", "solar:cpu-bold-duotone"),
                                            metric_card("Intel CPU (vCPU)", f"{totals.get('intel_cpu_total', 0.0):.1f}", "solar:cpu-bold-duotone"),
                                            metric_card("HANA CPU (vCPU)", f"{totals.get('power_cpu_total', 0.0):.1f}", "solar:cpu-bold-duotone", color="orange"),
                                        ],
                                    ),
                                ],
                            ),
                            html.Div(
                                className="nexus-card",
                                style={"padding": "20px"},
                                children=[
                                    html.H3("Backup summary", style={"margin": "0 0 12px 0", "color": "#2B3674"}),
                                    dmc.SimpleGrid(
                                        cols=3,
                                        spacing="lg",
                                        children=[
                                            metric_card("Veeam sessions", veeam_defined, "material-symbols:backup-outline"),
                                            metric_card("Protected VMs (Zerto)", zerto_protected, "material-symbols:shield-outline", color="teal"),
                                            metric_card("IBM storage volume (GB)", f"{storage_gb:.1f}", "solar:hdd-bold-duotone", color="orange"),
                                        ],
                                    ),
                                ],
                            ),
                            html.Div(
                                className="nexus-card",
                                style={"padding": "20px"},
                                children=[
                                    html.H3("Backup capacity (billing view)", style={"margin": "0 0 12px 0", "color": "#2B3674"}),
                                    dmc.SimpleGrid(
                                        cols=3,
                                        spacing="lg",
                                        children=[
                                            metric_card("NetBackup pre‑dedup (GiB)", f"{netbackup_pre_gib:.2f}", "mdi:database-lock-outline"),
                                            metric_card("NetBackup stored (GiB)", f"{netbackup_post_gib:.2f}", "mdi:database-arrow-down-outline", color="teal"),
                                            metric_card("Zerto max provisioned (GiB)", f"{zerto_provisioned_gib:.2f}", "solar:hdd-bold-duotone", color="orange"),
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    ),
                ),
                dmc.TabsPanel(
                    value="intel",
                    children=dmc.Stack(
                        gap="lg",
                        style={"padding": "0 30px"},
                        children=[
                            dmc.SimpleGrid(
                                cols=4,
                                spacing="lg",
                                children=[
                                    metric_card("Total Intel VMs", intel_vms.get("total", 0), "solar:laptop-bold-duotone", color="teal"),
                                    metric_card("Total CPU (Intel)", intel_cpu.get("total", 0.0), "solar:cpu-bold-duotone"),
                                    metric_card("Total Memory (Intel, GB)", f"{intel_mem.get('total', 0.0):.1f}", "solar:ram-bold-duotone"),
                                    metric_card("Total Disk (Intel, GB)", f"{intel_disk.get('total', 0.0):.1f}", "solar:hdd-bold-duotone", color="orange"),
                                ],
                            ),
                            html.Div(
                                className="nexus-card",
                                style={"padding": "20px"},
                                children=[
                                    html.H3("Platform breakdown (Intel)", style={"margin": "0 0 12px 0", "color": "#2B3674"}),
                                    dmc.Stack(
                                        gap="sm",
                                        children=[
                                            dmc.Group(
                                                justify="space-between",
                                                children=[
                                                    dmc.Text("VMware", size="sm", c="#A3AED0"),
                                                    dmc.Text(
                                                        f"VMs: {intel_vms.get('vmware', 0)}, CPU: {intel_cpu.get('vmware', 0.0):.1f}",
                                                        size="sm",
                                                        fw=600,
                                                    ),
                                                ],
                                            ),
                                            dmc.Group(
                                                justify="space-between",
                                                children=[
                                                    dmc.Text("Nutanix", size="sm", c="#A3AED0"),
                                                    dmc.Text(
                                                        f"VMs: {intel_vms.get('nutanix', 0)}, CPU: {intel_cpu.get('nutanix', 0.0):.1f}",
                                                        size="sm",
                                                        fw=600,
                                                    ),
                                                ],
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            html.Div(
                                className="nexus-card",
                                style={"padding": "20px"},
                                children=[
                                    html.H3("Intel VMs of customer", style={"margin": "0 0 12px 0", "color": "#2B3674"}),
                                    html.Div(
                                        style={"maxHeight": "400px", "overflowY": "auto"},
                                        children=[
                                            dmc.Table(
                                                striped=True,
                                                highlightOnHover=True,
                                                children=[
                                                    html.Thead(
                                                        html.Tr(
                                                            [
                                                                html.Th("VM"),
                                                                html.Th("Source"),
                                                                html.Th("CPU (vCPU)"),
                                                                html.Th("Memory (GB)"),
                                                                html.Th("Disk (GB)"),
                                                            ]
                                                        )
                                                    ),
                                                    html.Tbody(
                                                        [
                                                            html.Tr(
                                                                [
                                                                    html.Td(row.get("name")),
                                                                    html.Td(row.get("source")),
                                                                    html.Td(f"{row.get('cpu', 0.0):.1f}"),
                                                                    html.Td(f"{row.get('memory_gb', 0.0):.1f}"),
                                                                    html.Td(f"{row.get('disk_gb', 0.0):.1f}"),
                                                                ]
                                                            )
                                                            for row in intel_vm_list
                                                        ]
                                                        if intel_vm_list
                                                        else [html.Tr([html.Td("No data", colSpan=5)])]
                                                    ),
                                                ],
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    ),
                ),
                dmc.TabsPanel(
                    value="hana",
                    children=dmc.Stack(
                        gap="lg",
                        style={"padding": "0 30px"},
                        children=[
                            dmc.SimpleGrid(
                                cols=3,
                                spacing="lg",
                                children=[
                                    metric_card("HANA VMs (LPARs)", power_lpars, "solar:laptop-bold-duotone", color="teal"),
                                    metric_card("Total CPU (Power HMC)", f"{power_cpu:.1f}", "solar:cpu-bold-duotone"),
                                    metric_card("Total Memory (Power HMC, GB)", f"{power_mem:.1f}", "solar:ram-bold-duotone", color="orange"),
                                ],
                            ),
                            html.Div(
                                className="nexus-card",
                                style={"padding": "20px"},
                                children=[
                                    html.H3("HANA resource distribution", style={"margin": "0 0 12px 0", "color": "#2B3674"}),
                                    dcc.Graph(
                                        figure={
                                            "data": [
                                                go.Bar(name="CPU (vCPU)", x=["HANA"], y=[power_cpu]),
                                                go.Bar(name="Memory (GB)", x=["HANA"], y=[power_mem]),
                                            ],
                                            "layout": go.Layout(
                                                barmode="group",
                                                margin={"l": 40, "r": 10, "t": 10, "b": 40},
                                                height=260,
                                            ),
                                        },
                                        config={"displayModeBar": False},
                                    ),
                                ],
                            ),
                            html.Div(
                                className="nexus-card",
                                style={"padding": "20px"},
                                children=[
                                    html.H3("HANA VMs (LPARs) of customer", style={"margin": "0 0 12px 0", "color": "#2B3674"}),
                                    html.Div(
                                        style={"maxHeight": "400px", "overflowY": "auto"},
                                        children=[
                                            dmc.Table(
                                                striped=True,
                                                highlightOnHover=True,
                                                children=[
                                                    html.Thead(
                                                        html.Tr(
                                                            [
                                                                html.Th("LPAR"),
                                                                html.Th("Source"),
                                                                html.Th("CPU (vCPU)"),
                                                                html.Th("Memory (GB)"),
                                                                html.Th("State"),
                                                            ]
                                                        )
                                                    ),
                                                    html.Tbody(
                                                        [
                                                            html.Tr(
                                                                [
                                                                    html.Td(row.get("name")),
                                                                    html.Td(row.get("source")),
                                                                    html.Td(f"{row.get('cpu', 0.0):.1f}"),
                                                                    html.Td(f"{row.get('memory_gb', 0.0):.1f}"),
                                                                    html.Td(row.get("state") or "-"),
                                                                ]
                                                            )
                                                            for row in power_vm_list
                                                        ]
                                                        if power_vm_list
                                                        else [html.Tr([html.Td("No data", colSpan=5)])]
                                                    ),
                                                ],
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    ),
                ),
                dmc.TabsPanel(
                    value="backup",
                    children=dmc.Stack(
                        gap="lg",
                        style={"padding": "0 30px"},
                        children=[
                            dmc.SimpleGrid(
                                cols=3,
                                spacing="lg",
                                children=[
                                    metric_card("Veeam sessions", veeam_defined, "material-symbols:backup-outline"),
                                    metric_card("Protected VMs (Zerto)", zerto_protected, "material-symbols:shield-outline", color="teal"),
                                    metric_card("NetBackup dedup factor", netbackup_dedup_factor, "mdi:percent-outline", color="orange"),
                                ],
                            ),
                            html.Div(
                                className="nexus-card",
                                style={"padding": "20px"},
                                children=[
                                    html.H3("NetBackup billing summary", style={"margin": "0 0 12px 0", "color": "#2B3674"}),
                                    dmc.SimpleGrid(
                                        cols=3,
                                        spacing="lg",
                                        children=[
                                            metric_card("Pre‑dedup size (GiB)", f"{netbackup_pre_gib:.2f}", "mdi:database-lock-outline"),
                                            metric_card("Stored size (GiB)", f"{netbackup_post_gib:.2f}", "mdi:database-arrow-down-outline", color="teal"),
                                            metric_card("Dedup factor", netbackup_dedup_factor, "mdi:percent-outline", color="orange"),
                                        ],
                                    ),
                                ],
                            ),
                            html.Div(
                                className="nexus-card",
                                style={"padding": "20px"},
                                children=[
                                    html.H3("Veeam sessions by type", style={"margin": "0 0 12px 0", "color": "#2B3674"}),
                                    html.Div(
                                        style={"maxHeight": "300px", "overflowY": "auto"},
                                        children=[
                                            dmc.Table(
                                                striped=True,
                                                highlightOnHover=True,
                                                children=[
                                                    html.Thead(html.Tr([html.Th("Session type"), html.Th("Defined sessions")])),
                                                    html.Tbody(
                                                        [
                                                            html.Tr([html.Td(row.get("type")), html.Td(row.get("count", 0))])
                                                            for row in veeam_types
                                                        ]
                                                        if veeam_types
                                                        else [html.Tr([html.Td("No data", colSpan=2)])]
                                                    ),
                                                ],
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            html.Div(
                                className="nexus-card",
                                style={"padding": "20px"},
                                children=[
                                    html.H3("Zerto VPGs (last 30 days max provisioned)", style={"margin": "0 0 12px 0", "color": "#2B3674"}),
                                    html.Div(
                                        style={"maxHeight": "300px", "overflowY": "auto"},
                                        children=[
                                            dmc.Table(
                                                striped=True,
                                                highlightOnHover=True,
                                                children=[
                                                    html.Thead(html.Tr([html.Th("VPG Name"), html.Th("Provisioned Storage (GiB)")])),
                                                    html.Tbody(
                                                        [
                                                            html.Tr(
                                                                [
                                                                    html.Td(row.get("name")),
                                                                    html.Td(f"{row.get('provisioned_storage_gib', 0.0):.2f}"),
                                                                ]
                                                            )
                                                            for row in zerto_vpgs
                                                        ]
                                                        if zerto_vpgs
                                                        else [html.Tr([html.Td("No data", colSpan=2)])]
                                                    ),
                                                ],
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    ),
                ),
            ],
        ),
    ]
