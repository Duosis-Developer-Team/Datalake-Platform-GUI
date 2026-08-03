"""Platform Versions panelinin saf render yardımcıları.

Burada veri çekilmez; her fonksiyon aldığı sözlükten bileşen üretir. Panelin iki katı
kuralı bu modülde yaşar:
  1. Yalnızca `body` gösterilir; `draft_body` panele hiç girmez.
  2. Ham commit subject'i yalnızca katlanmış "Teknik detay" bölümünde durur.
"""

from __future__ import annotations

import dash_mantine_components as dmc
from dash import html
from dash_iconify import DashIconify

from src.utils.ui_tokens import ON_SURFACE, relative_time

# (anahtar, Türkçe etiket, renk, ikon)
BUCKETS = (
    ("added", "Yenilikler", "teal", "solar:star-bold-duotone"),
    ("fixed", "Düzeltmeler", "orange", "solar:bug-bold-duotone"),
    ("improved", "İyileştirmeler", "grape", "solar:bolt-bold-duotone"),
)

# Teknik detay bölümünde gösterilen commit tipleri.
_CHANGE_TYPES = (
    ("feat", "Features", "teal"),
    ("fix", "Fixes", "orange"),
    ("perf", "Performance", "grape"),
)

_TR_MONTHS = (
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
)

_ACCENT = "var(--mantine-color-indigo-6)"
_ACCENT_SOFT = "var(--mantine-color-indigo-0)"
_LIVE = "var(--mantine-color-teal-6)"
_RAIL = "var(--mantine-color-gray-3)"
_ON_ACCENT = "var(--mantine-color-white)"


# --- veri yardımcıları ----------------------------------------------------

def group_changes(changes: list[dict]) -> tuple[dict[str, list[dict]], int]:
    groups: dict[str, list[dict]] = {t[0]: [] for t in _CHANGE_TYPES}
    internal = 0
    for c in changes or []:
        t = str(c.get("change_type") or "other")
        if t in groups:
            groups[t].append(c)
        else:
            internal += 1
    return groups, internal


def note_body(rel: dict) -> dict:
    note = rel.get("note") or {}
    body = note.get("body")
    return body if isinstance(body, dict) else {}


def note_source(rel: dict) -> str:
    note = rel.get("note") or {}
    return str(note.get("source") or "auto")


def note_headline(rel: dict) -> str | None:
    note = rel.get("note") or {}
    headline = note.get("headline")
    return str(headline) if headline else None


def bucket_counts(body: dict) -> dict[str, int]:
    return {key: len((body or {}).get(key) or []) for key, _l, _c, _i in BUCKETS}


def auto_summary_line(body: dict) -> str:
    """Kartta gösterilen, tamamen kodda hesaplanan Türkçe özet."""
    counts = bucket_counts(body)
    words = {"added": "yenilik", "fixed": "düzeltme", "improved": "iyileştirme"}
    parts = [f"{counts[k]} {words[k]}" for k in ("added", "fixed", "improved") if counts[k]]
    if not parts:
        return "Bu sürümde kullanıcıya dönük değişiklik yok."
    # Türkçe liste: son iki öğe "ve" ile, öncekiler virgülle. Hepsini "ve" ile
    # bağlamak üç kova dolduğunda "a ve b ve c" gibi okunuyordu.
    listed = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " ve " + parts[-1]
    return f"Bu sürümde {listed} var."


def resolve_live_version(releases: list[dict], current: list[dict]) -> str | None:
    version = None
    if current:
        newest = max(current, key=lambda d: str(d.get("started_at") or ""))
        version = str(newest.get("version") or "").strip() or None
    if not version and releases:
        version = str(releases[0].get("version") or "").strip() or None
    return version


def is_live(rel: dict, live_version: str | None) -> bool:
    if not live_version:
        return False
    return str(rel.get("version") or "").strip() == str(live_version).strip()


def matches_search(rel: dict, term: str) -> bool:
    needle = (term or "").strip().lower()
    if not needle:
        return True
    haystack = [str(rel.get("version") or ""), note_headline(rel) or ""]
    body = note_body(rel)
    for key, _l, _c, _i in BUCKETS:
        for item in body.get(key) or []:
            haystack.append(str((item or {}).get("text") or ""))
    for c in rel.get("changes") or []:
        haystack.append(str(c.get("summary") or ""))
    return needle in " ".join(haystack).lower()


def month_label(iso_date: str) -> str:
    text = str(iso_date or "")[:10]
    try:
        year, month = int(text[:4]), int(text[5:7])
        return f"{_TR_MONTHS[month - 1]} {year}"
    except (ValueError, IndexError):
        return "Tarihsiz"


# --- bileşenler -----------------------------------------------------------

def _bullet_rows(items: list[dict], color: str) -> list:
    return [
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
                dmc.Text(str((item or {}).get("text") or ""), size="sm", c=ON_SURFACE),
            ],
        )
        for item in items
    ]


def _count_badges(body: dict) -> dmc.Group | None:
    counts = bucket_counts(body)
    chips = [
        dmc.Badge(f"{counts[key]} {label}", color=color, variant="light", size="sm", radius="sm")
        for key, label, color, _icon in BUCKETS
        if counts[key]
    ]
    return dmc.Group(gap="xs", children=chips) if chips else None


def headline_block(rel: dict) -> dmc.Stack:
    """Kartın gövdesi. Ham commit subject'i buraya asla girmez."""
    body = note_body(rel)
    source = note_source(rel)
    children: list = []

    headline = note_headline(rel)
    if headline:
        children.append(dmc.Text(headline, fw=600, size="md", c=ON_SURFACE))

    badges = _count_badges(body)
    if badges:
        children.append(badges)

    if source == "model":
        for key, label, color, icon in BUCKETS:
            items = body.get(key) or []
            if not items:
                continue
            children.append(
                dmc.Stack(
                    gap=5,
                    children=[
                        dmc.Group(
                            gap=6,
                            align="center",
                            children=[
                                DashIconify(icon=icon, width=14, color=f"var(--mantine-color-{color}-6)"),
                                dmc.Text(
                                    label, size="xs", fw=700, tt="uppercase",
                                    c=f"var(--mantine-color-{color}-7)",
                                ),
                            ],
                        ),
                        *_bullet_rows(items, color),
                    ],
                )
            )
    else:
        children.append(dmc.Text(auto_summary_line(body), size="sm", c=ON_SURFACE))
        children.append(
            dmc.Badge("otomatik özet", variant="light", color="gray", size="xs", radius="sm")
        )

    return dmc.Stack(gap=10, children=children)


def technical_section(rel: dict) -> dmc.Accordion:
    """Ham commit'ler ve service deployment kayıtları — varsayılan olarak kapalı."""
    groups, internal = group_changes(rel.get("changes") or [])
    rows: list = []
    for key, label, color in _CHANGE_TYPES:
        items = groups[key]
        if not items:
            continue
        rows.append(
            dmc.Text(label, size="xs", fw=700, tt="uppercase", c=f"var(--mantine-color-{color}-7)")
        )
        for c in items:
            rows.append(
                dmc.Group(
                    gap="sm",
                    wrap="nowrap",
                    children=[
                        dmc.Text(
                            str(c.get("commit_sha") or "—"), size="xs", c="dimmed", ff="monospace"
                        ),
                        dmc.Text(str(c.get("summary") or ""), size="xs", c="dimmed"),
                    ],
                )
            )
    if internal:
        rows.append(dmc.Text(f"+{internal} internal change", size="xs", c="dimmed"))

    for s in rel.get("services") or []:
        rows.append(
            dmc.Group(
                gap="sm",
                children=[
                    dmc.Badge(str(s.get("service") or "—"), variant="light", color="indigo", size="sm"),
                    dmc.Text(f"sha {s.get('git_sha') or '—'}", size="xs", c="dimmed", ff="monospace"),
                    dmc.Text(str(s.get("started_at") or "")[:19], size="xs", c="dimmed"),
                ],
            )
        )
    if not rows:
        rows.append(dmc.Text("Kayıtlı teknik detay yok.", size="xs", c="dimmed"))

    return dmc.Accordion(
        variant="filled",
        chevronPosition="left",
        styles={"control": {"paddingLeft": 0, "paddingRight": 0}},
        children=[
            dmc.AccordionItem(
                value="tech",
                children=[
                    dmc.AccordionControl(dmc.Text("Teknik detay", size="xs", fw=600, c="dimmed")),
                    dmc.AccordionPanel(dmc.Stack(gap=6, children=rows)),
                ],
            )
        ],
    )


def _version_line(rel: dict, *, live: bool, size: str) -> dmc.Group:
    left = [dmc.Text(str(rel.get("version") or ""), fw=800, size=size, c=ON_SURFACE)]
    if live:
        left.append(dmc.Badge("Yayında", color="teal", variant="filled", size="sm", radius="sm"))
    return dmc.Group(
        justify="space-between",
        align="center",
        wrap="nowrap",
        children=[
            dmc.Group(gap="xs", align="center", children=left),
            dmc.Text(
                f"{str(rel.get('released_at') or '')[:10]} · {relative_time(rel.get('released_at'))}",
                size="xs",
                c="dimmed",
            ),
        ],
    )


def regenerate_button(version: str) -> dmc.Button:
    """Notu yeniden ürettiren düğme.

    Yalnızca yetkisi olana çizilir; asıl kontrol callback'in içindedir, çünkü
    görünürlük tek başına yetki değildir.
    """
    return dmc.Button(
        "Yeniden üret",
        id={"type": "pv-regen", "version": str(version)},
        variant="subtle",
        size="xs",
        color="indigo",
        leftSection=DashIconify(icon="solar:refresh-bold-duotone", width=14),
    )


def _regenerate_row(rel: dict) -> dmc.Group:
    return dmc.Group(
        justify="flex-end",
        children=[regenerate_button(str(rel.get("version") or ""))],
    )


def hero_card(rel: dict, *, live: bool = True, can_regenerate: bool = False) -> dmc.Paper:
    """Listenin başındaki büyük kart. `live=False` ise "Yayında" rozeti çizilmez."""
    children: list = [_version_line(rel, live=live, size="xl")]
    if can_regenerate:
        children.append(_regenerate_row(rel))
    children.append(headline_block(rel))
    children.append(technical_section(rel))
    return dmc.Paper(
        withBorder=True,
        radius="md",
        p="lg",
        style={"borderColor": _ACCENT, "background": _ACCENT_SOFT},
        children=dmc.Stack(gap=12, children=children),
    )


def history_row(rel: dict, *, can_regenerate: bool = False) -> dmc.AccordionItem:
    """Geçmiş sürüm — kapalı satır, açılınca notu gösterir."""
    panel: list = [headline_block(rel), technical_section(rel)]
    if can_regenerate:
        panel.append(_regenerate_row(rel))
    return dmc.AccordionItem(
        value=str(rel.get("version") or ""),
        children=[
            dmc.AccordionControl(_version_line(rel, live=False, size="md")),
            dmc.AccordionPanel(dmc.Stack(gap=12, children=panel)),
        ],
    )


def _stat(value: str, label: str) -> html.Div:
    return html.Div(
        children=[
            dmc.Text(value, fw=800, size="xl", c=_ACCENT, style={"lineHeight": 1.1}),
            dmc.Text(label, size="xs", c="dimmed", tt="uppercase", fw=600),
        ]
    )


def stat_strip(releases: list[dict], live_version: str | None) -> dmc.Paper:
    """Altındaki listeyi özetler; sayılar hep gösterilen release'lerden hesaplanır."""
    total_changes = sum(len(r.get("changes") or []) for r in releases)
    with_notes = sum(1 for r in releases if note_source(r) == "model")
    return dmc.Paper(
        withBorder=True,
        radius="md",
        p="md",
        mb="lg",
        children=dmc.Group(
            gap="xl",
            children=[
                _stat(str(len(releases)), "sürüm"),
                _stat(str(total_changes), "değişiklik"),
                _stat(str(with_notes), "yazılmış not"),
                _stat(live_version or "—", "yayındaki sürüm"),
            ],
        ),
    )


def release_list(
    releases: list[dict], live_version: str | None, *, can_regenerate: bool = False
) -> html.Div:
    """Hero kartı + ay ayraçlarıyla ayrılmış geçmiş satırları."""
    if not releases:
        return html.Div(
            dmc.Text("Aramanla eşleşen sürüm yok.", size="sm", c="dimmed")
        )

    children: list = []
    hero_index = None
    for i, rel in enumerate(releases):
        if is_live(rel, live_version):
            hero_index = i
            break
    hero_is_live = hero_index is not None
    if hero_index is None:
        hero_index = 0
    children.append(
        hero_card(releases[hero_index], live=hero_is_live, can_regenerate=can_regenerate)
    )

    rest = [r for i, r in enumerate(releases) if i != hero_index]
    current_month = None
    items: list = []
    for rel in rest:
        label = month_label(rel.get("released_at"))
        if label != current_month:
            if items:
                children.append(dmc.Accordion(variant="separated", chevronPosition="left", children=items))
                items = []
            current_month = label
            children.append(
                dmc.Divider(
                    label=label,
                    labelPosition="left",
                    mt="lg",
                    mb="xs",
                    color=_RAIL,
                )
            )
        items.append(history_row(rel, can_regenerate=can_regenerate))
    if items:
        children.append(dmc.Accordion(variant="separated", chevronPosition="left", children=items))

    return html.Div(children)


def search_panel(
    releases: list[dict],
    live_version: str | None,
    term: str,
    *,
    can_regenerate: bool = False,
) -> html.Div:
    """Arama sonucunun tamamı: onu özetleyen şerit + kartlar.

    `versions.render_list` ile aynı düzeni kurar; farkı, yetkiye göre "Yeniden üret"
    düğmesini de çizebilmesidir. Şerit listeyle birlikte hesaplanır, böylece sayılar
    hep ekranda duran release'leri anlatır.
    """
    visible = [r for r in releases if matches_search(r, term)]
    shown_live = live_version if any(is_live(r, live_version) for r in visible) else None
    return html.Div(
        [
            stat_strip(visible, shown_live),
            release_list(visible, shown_live, can_regenerate=can_regenerate),
        ]
    )
