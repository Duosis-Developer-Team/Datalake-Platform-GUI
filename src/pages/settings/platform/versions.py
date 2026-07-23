"""Platform version history (changelog) timeline."""

from __future__ import annotations

import dash_mantine_components as dmc
from dash import html

from src.services import admin_client
from src.utils.ui_tokens import ON_SURFACE, relative_time, section_header, settings_page_shell

_VISIBLE_TYPES = ("feat", "fix", "perf")
_TYPE_COLOR = {"feat": "teal", "fix": "orange", "perf": "grape"}
_TYPE_LABEL = {"feat": "Feature", "fix": "Fix", "perf": "Perf"}


def _split_changes(changes: list[dict]) -> tuple[list[dict], int]:
    visible = [c for c in changes if (c.get("change_type") or "other") in _VISIBLE_TYPES]
    hidden = len(changes) - len(visible)
    return visible, hidden


def _service_rows(services: list[dict]) -> html.Div | dmc.Stack | dmc.Text:
    if not services:
        return dmc.Text("No deployment records for this version.", size="xs", c="dimmed")
    rows = []
    for s in services:
        rows.append(
            dmc.Group(
                gap="sm",
                children=[
                    dmc.Badge(str(s.get("service") or "—"), variant="light", color="indigo", size="sm"),
                    dmc.Text(f"sha {s.get('git_sha') or '—'}", size="xs", c="dimmed"),
                    dmc.Text(str(s.get("started_at") or "")[:19], size="xs", c="dimmed"),
                ],
            )
        )
    return dmc.Stack(gap=4, children=rows)


def _release_card(rel: dict, *, is_live: bool) -> dmc.Paper:
    visible, hidden = _split_changes(rel.get("changes") or [])
    change_items = [
        dmc.Group(
            gap="xs",
            children=[
                dmc.Badge(
                    _TYPE_LABEL.get(c.get("change_type"), "Change"),
                    variant="light",
                    color=_TYPE_COLOR.get(c.get("change_type"), "gray"),
                    size="xs",
                ),
                dmc.Text(str(c.get("summary") or ""), size="sm"),
            ],
        )
        for c in visible
    ]
    if hidden:
        change_items.append(dmc.Text(f"+{hidden} technical changes", size="xs", c="dimmed"))

    version_group_children = [dmc.Text(rel.get("version", ""), fw=700, c=ON_SURFACE)]
    if is_live:
        version_group_children.append(dmc.Badge("Live", color="green", variant="filled", size="sm"))

    header = dmc.Group(
        justify="space-between",
        children=[
            dmc.Group(gap="sm", children=version_group_children),
            dmc.Text(
                f"{rel.get('released_at', '')} · {relative_time(rel.get('released_at'))}",
                size="xs",
                c="dimmed",
            ),
        ],
    )
    body = (
        dmc.Stack(gap=6, children=change_items)
        if change_items
        else dmc.Text("No user-facing changes.", size="xs", c="dimmed")
    )
    return dmc.Paper(
        withBorder=True,
        radius="md",
        p="md",
        children=[
            header,
            dmc.Space(h=8),
            body,
            dmc.Space(h=10),
            dmc.Accordion(
                variant="separated",
                chevronPosition="left",
                children=[
                    dmc.AccordionItem(
                        value="svc",
                        children=[
                            dmc.AccordionControl(dmc.Text("Service deployments", size="xs", c="dimmed")),
                            dmc.AccordionPanel(_service_rows(rel.get("services") or [])),
                        ],
                    )
                ],
            ),
        ],
    )


def build_layout(search: str | None = None) -> html.Div:
    releases = admin_client.list_platform_releases()
    current = admin_client.get_current_versions()
    live_version = None
    if current:
        live_version = max(current, key=lambda d: str(d.get("started_at") or "")).get("version")

    if not releases:
        body = dmc.Paper(
            withBorder=True,
            radius="md",
            p="xl",
            children=dmc.Text(
                "No version history yet. Run the backfill script to populate it.",
                c="dimmed",
            ),
        )
    else:
        body = dmc.Stack(
            gap="md",
            children=[_release_card(r, is_live=(r.get("version") == live_version)) for r in releases],
        )

    return html.Div(
        settings_page_shell(
            [
                section_header(
                    "Platform versions",
                    "Deployed versions from first release to today, with changelog.",
                    icon="solar:box-bold-duotone",
                ),
                body,
            ]
        )
    )
