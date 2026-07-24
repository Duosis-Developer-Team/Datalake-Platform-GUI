"""Platform version history — a changelog timeline grouped by change type."""

from __future__ import annotations

import dash_mantine_components as dmc
from dash import html
from dash_iconify import DashIconify

from src.services import admin_client
from src.utils.ui_tokens import ON_SURFACE, relative_time, section_header, settings_page_shell

# Change types we surface to readers, in narrative order, with their identity.
# Everything else (chore, refactor, docs, build…) folds into an "internal" count.
_TYPES = (
    ("feat", "Features", "teal", "solar:star-bold-duotone"),
    ("fix", "Fixes", "orange", "solar:bug-bold-duotone"),
    ("perf", "Performance", "grape", "solar:bolt-bold-duotone"),
)


def _group_changes(changes: list[dict]) -> tuple[dict[str, list[dict]], int]:
    groups: dict[str, list[dict]] = {t[0]: [] for t in _TYPES}
    internal = 0
    for c in changes or []:
        t = c.get("change_type") or "other"
        if t in groups:
            groups[t].append(c)
        else:
            internal += 1
    return groups, internal


def _summary_chips(groups: dict[str, list[dict]]) -> dmc.Group | None:
    chips = [
        dmc.Badge(f"{len(groups[key])} {label}", color=color, variant="light", size="sm", radius="sm")
        for key, label, color, _icon in _TYPES
        if groups[key]
    ]
    return dmc.Group(gap="xs", children=chips) if chips else None


def _grouped_body(groups: dict[str, list[dict]]) -> dmc.Stack:
    sections = []
    for key, label, color, icon in _TYPES:
        items = groups[key]
        if not items:
            continue
        rows = [
            dmc.Group(
                gap=8,
                align="flex-start",
                wrap="nowrap",
                children=[
                    html.Div(
                        style={
                            "width": 5, "height": 5, "borderRadius": "50%",
                            "background": f"var(--mantine-color-{color}-5)",
                            "marginTop": 8, "flexShrink": 0,
                        }
                    ),
                    dmc.Text(str(c.get("summary") or ""), size="sm", c=ON_SURFACE),
                ],
            )
            for c in items
        ]
        sections.append(
            dmc.Stack(
                gap=5,
                children=[
                    dmc.Group(
                        gap=6,
                        align="center",
                        children=[
                            DashIconify(icon=icon, width=14, color=f"var(--mantine-color-{color}-6)"),
                            dmc.Text(label, size="xs", fw=700, tt="uppercase", c=f"var(--mantine-color-{color}-7)"),
                        ],
                    ),
                    *rows,
                ],
            )
        )
    return dmc.Stack(gap=16, children=sections)


def _service_rows(services: list[dict]) -> dmc.Stack | dmc.Text:
    if not services:
        return dmc.Text("Not recorded against any service yet.", size="xs", c="dimmed")
    return dmc.Stack(
        gap=6,
        children=[
            dmc.Group(
                gap="sm",
                children=[
                    dmc.Badge(str(s.get("service") or "—"), variant="light", color="indigo", size="sm"),
                    dmc.Text(f"sha {s.get('git_sha') or '—'}", size="xs", c="dimmed", ff="monospace"),
                    dmc.Text(str(s.get("started_at") or "")[:19], size="xs", c="dimmed"),
                ],
            )
            for s in services
        ],
    )


def _release_item(rel: dict, *, is_live: bool, is_last: bool) -> html.Div:
    groups, internal = _group_changes(rel.get("changes") or [])
    has_visible = any(groups[k] for k in groups)

    version_children = [dmc.Text(rel.get("version", ""), fw=800, size="lg", c=ON_SURFACE)]
    if is_live:
        version_children.append(dmc.Badge("Live", color="green", variant="filled", size="sm", radius="sm"))

    title = dmc.Group(
        justify="space-between",
        align="center",
        wrap="nowrap",
        children=[
            dmc.Group(gap="xs", align="center", children=version_children),
            dmc.Text(
                f"{str(rel.get('released_at', ''))[:10]} · {relative_time(rel.get('released_at'))}",
                size="xs",
                c="dimmed",
            ),
        ],
    )

    body: list = []
    chips = _summary_chips(groups)
    if chips:
        body.append(chips)
    if has_visible:
        body.append(
            dmc.Spoiler(
                showLabel="Show all changes",
                hideLabel="Show less",
                maxHeight=176,
                children=_grouped_body(groups),
            )
        )
    else:
        body.append(dmc.Text("No user-facing changes in this release.", size="sm", c="dimmed"))
    if internal:
        body.append(dmc.Text(f"+{internal} internal changes", size="xs", c="dimmed"))

    body.append(
        dmc.Accordion(
            variant="filled",
            chevronPosition="left",
            styles={"control": {"paddingLeft": 0, "paddingRight": 0}},
            children=[
                dmc.AccordionItem(
                    value="svc",
                    children=[
                        dmc.AccordionControl(
                            dmc.Text("Service deployments", size="xs", fw=600, c="dimmed")
                        ),
                        dmc.AccordionPanel(_service_rows(rel.get("services") or [])),
                    ],
                )
            ],
        )
    )

    dot = html.Div(
        style={
            "width": 22, "height": 22, "borderRadius": "50%",
            "background": "#12B76A" if is_live else "#EEF0FF",
            "border": "2px solid #12B76A" if is_live else "2px solid #4318FF",
            "display": "flex", "alignItems": "center", "justifyContent": "center",
            "flexShrink": 0, "zIndex": 1,
        },
        children=DashIconify(
            icon="solar:check-circle-bold" if is_live else "solar:box-minimalistic-bold-duotone",
            width=12,
            color="#FFFFFF" if is_live else "#4318FF",
        ),
    )
    rail_children = [dot]
    if not is_last:
        rail_children.append(
            html.Div(style={"width": 2, "flexGrow": 1, "background": "#E3EAFC", "marginTop": 2})
        )
    rail = html.Div(
        style={"display": "flex", "flexDirection": "column", "alignItems": "center", "width": 22, "flexShrink": 0},
        children=rail_children,
    )

    card = dmc.Paper(
        withBorder=True,
        radius="md",
        p="md",
        children=dmc.Stack(gap=10, children=[title, *[c for c in body if c is not None]]),
    )

    return html.Div(
        style={"display": "flex", "gap": 16, "paddingBottom": 0 if is_last else 20},
        children=[rail, html.Div(card, style={"flex": 1, "minWidth": 0})],
    )


def _count_stat(value: str, label: str) -> html.Div:
    return html.Div(
        children=[
            dmc.Text(value, fw=800, size="xl", c="#4318FF", style={"lineHeight": 1.1}),
            dmc.Text(label, size="xs", c="dimmed", tt="uppercase", fw=600),
        ]
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
            children=dmc.Stack(
                gap=4,
                children=[
                    dmc.Text("No version history yet.", fw=600, c=ON_SURFACE),
                    dmc.Text(
                        "Run scripts/backfill_platform_versions.py to build it from git history.",
                        c="dimmed",
                        size="sm",
                    ),
                ],
            ),
        )
    else:
        total_changes = sum(len(r.get("changes") or []) for r in releases)
        count_strip = dmc.Group(
            gap="xl",
            mb="lg",
            children=[
                _count_stat(str(len(releases)), "releases"),
                _count_stat(str(total_changes), "changes"),
                _count_stat(live_version or "—", "live version"),
            ],
        )
        n = len(releases)
        body = html.Div(
            [
                count_strip,
                html.Div(
                    children=[
                        _release_item(
                            r,
                            is_live=(r.get("version") == live_version),
                            is_last=(i == n - 1),
                        )
                        for i, r in enumerate(releases)
                    ]
                ),
            ]
        )

    return html.Div(
        settings_page_shell(
            [
                section_header(
                    "Platform versions",
                    "Every release from launch to today, with its changelog.",
                    icon="solar:box-bold-duotone",
                ),
                body,
            ]
        )
    )
