"""Platform sürüm geçmişi — her release'in okunabilir notuyla birlikte."""

from __future__ import annotations

from urllib.parse import parse_qs

import dash_mantine_components as dmc
from dash import html

from src.pages.settings.platform import versions_view as vv
from src.services import admin_client
from src.utils.ui_tokens import ON_SURFACE, section_header, settings_page_shell

SEARCH_ID = "platform-versions-search"
LIST_ID = "platform-versions-list"


def _search_term(search: str | None) -> str:
    if not search:
        return ""
    values = parse_qs(str(search).lstrip("?")).get("q") or [""]
    return values[0].strip()


def load_releases() -> tuple[list[dict], str | None]:
    releases = admin_client.list_platform_releases() or []
    current = admin_client.get_current_versions() or []
    return releases, vv.resolve_live_version(releases, current)


def render_list(releases: list[dict], live_version: str | None, term: str) -> html.Div:
    """Arama sonucunu çizer: üstte o sonucu özetleyen şerit, altında kartlar.

    Şerit de listeyle birlikte yenilenir; böylece sayılar hep ekranda duran
    release'leri anlatır ve arama sırasında görünmeyen bir sürümün numarası
    panele sızmaz.

    Düzenin kendisi `versions_view.search_panel` içinde durur; burası ilk boyama
    için yetkisiz (düğmesiz) hâlini ister. Tek kopya olsun diye delege ediyoruz —
    iki yerde ayrı ayrı hesaplanan bir şerit, zamanla ayrışır.
    """
    return vv.search_panel(releases, live_version, term, can_regenerate=False)


def _empty_state() -> dmc.Paper:
    return dmc.Paper(
        withBorder=True,
        radius="md",
        p="xl",
        children=dmc.Stack(
            gap=4,
            children=[
                dmc.Text("Henüz sürüm geçmişi yok.", fw=600, c=ON_SURFACE),
                dmc.Text(
                    "Geçmişi git'ten kurmak için scripts/backfill_platform_versions.py çalıştır.",
                    c="dimmed",
                    size="sm",
                ),
            ],
        ),
    )


def build_layout(search: str | None = None) -> html.Div:
    releases, live_version = load_releases()
    term = _search_term(search)

    if not releases:
        body: list = [_empty_state()]
    else:
        body = [
            dmc.TextInput(
                id=SEARCH_ID,
                placeholder="Sürüm, başlık veya değişiklik ara",
                value=term,
                mb="md",
                size="sm",
                debounce=300,
            ),
            html.Div(render_list(releases, live_version, term), id=LIST_ID),
        ]

    return html.Div(
        settings_page_shell(
            [
                section_header(
                    "Platform sürümleri",
                    "İlk günden bugüne her release ve neyi değiştirdiği.",
                    icon="solar:box-bold-duotone",
                ),
                *body,
            ]
        )
    )
