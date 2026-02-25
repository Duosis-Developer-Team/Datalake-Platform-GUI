import dash
import dash_mantine_components as dmc

from components.header import create_header
from components.navbar import create_navbar


def create_layout():
    return dmc.MantineProvider(
        dmc.AppShell(
            [
                dmc.AppShellHeader(create_header()),
                dmc.AppShellNavbar(create_navbar()),
                dmc.AppShellMain(dash.page_container),
            ],
            header={"height": 60},
            navbar={
                "width": 260,
                "breakpoint": "sm",
                "collapsed": {"mobile": True},
            },
            padding="xl",
        ),
        theme={"primaryColor": "indigo"},
        forceColorScheme="light",
    )
