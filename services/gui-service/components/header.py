import dash_mantine_components as dmc
from dash_iconify import DashIconify


def create_header():
    return dmc.Group(
        [
            DashIconify(icon="mdi:cloud-outline", width=30, color="#4c6ef5"),
            dmc.Title("Bulutistan", order=3, fw=800),
        ],
        h="100%",
        px="md",
        gap="xs",
    )
