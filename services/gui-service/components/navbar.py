import dash_mantine_components as dmc
from dash_iconify import DashIconify

NAV_ITEMS = [
    {
        "label": "Overview",
        "icon": "mdi:view-dashboard-outline",
        "href": "/overview",
        "description": "Platform genel bakış",
    },
    {
        "label": "Data Centers",
        "icon": "mdi:server-network",
        "href": "/datacenters",
        "description": "Veri merkezi listesi",
    },
    {
        "label": "Customs",
        "icon": "mdi:chart-box-outline",
        "href": "/customs",
        "description": "Özel raporlar (yakında)",
        "disabled": True,
    },
]


def create_navbar():
    links = [
        dmc.NavLink(
            label=item["label"],
            description=item.get("description"),
            leftSection=DashIconify(icon=item["icon"], width=20),
            href=item["href"],
            active="exact",
            disabled=item.get("disabled", False),
        )
        for item in NAV_ITEMS
    ]
    return dmc.Box(
        dmc.ScrollArea(
            dmc.Stack(links, gap=4),
            h="100%",
            p="md",
        ),
        className="sidebar-float",
        h="100%",
    )
