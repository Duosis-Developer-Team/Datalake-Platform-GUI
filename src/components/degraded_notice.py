"""Placeholder for a page whose data never arrived.

Distinct from an empty state. "No rows match this filter" and "this DC has no
unmapped resources" are answers; this is the absence of one. The pages used to
render the same zeros for both, so an operator looking at Overview during a
backend outage saw 0 hosts, 0 VMs and 0 kW — indistinguishable from every
datacenter going dark — and then watched the real figures reappear a callback
later. Saying nothing is known is both truthful and less alarming.

Carries no number, deliberately: any figure on this card would be read as a
measurement.
"""

from __future__ import annotations

import dash_mantine_components as dmc
from dash import html
from dash_iconify import DashIconify

DEGRADED_NOTICE_ID = "degraded-data-notice"


def build_degraded_notice(subject: str | None = None) -> html.Div:
    """Card explaining that the data could not be fetched.

    `subject` names what failed ("Data Center DC13") when the page is about one
    thing; omit it on pages that aggregate several sources.
    """
    detail = (
        f"{subject} verileri şu anda alınamıyor."
        if subject
        else "Veriler şu anda alınamıyor."
    )
    return html.Div(
        id=DEGRADED_NOTICE_ID,
        style={"maxWidth": "560px", "margin": "64px auto"},
        children=[
            dmc.Paper(
                p="xl",
                radius="lg",
                withBorder=True,
                children=[
                    dmc.Group(
                        gap="md",
                        align="flex-start",
                        children=[
                            DashIconify(
                                icon="solar:cloud-cross-bold-duotone",
                                width=40,
                                color="#F79009",
                            ),
                            dmc.Stack(
                                gap="xs",
                                children=[
                                    dmc.Text("Veri alınamadı", fw=800, size="xl"),
                                    dmc.Text(
                                        f"{detail} Sayfayı yenileyerek tekrar deneyin; "
                                        "sorun sürerse sistem yöneticinize bildirin.",
                                        size="sm",
                                        c="dimmed",
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )
