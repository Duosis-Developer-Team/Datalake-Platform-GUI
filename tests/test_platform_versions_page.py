"""Platform Versions paneli — saf render kuralları."""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

from src.pages.settings.platform import versions as page
from src.pages.settings.platform import versions_view as vv

SHA_A = "aaaaaaaaaaaa"
SHA_B = "bbbbbbbbbbbb"
MARKER = "ZZTOPMARKER"


def _flatten(node) -> list[str]:
    """Bileşen ağacındaki bütün metinleri toplar."""
    out: list[str] = []
    if node is None:
        return out
    if isinstance(node, (str, int, float)):
        return [str(node)]
    if isinstance(node, (list, tuple)):
        for n in node:
            out.extend(_flatten(n))
        return out
    out.extend(_flatten(getattr(node, "children", None)))
    for attr in ("label", "showLabel", "hideLabel", "placeholder"):
        v = getattr(node, attr, None)
        if isinstance(v, str):
            out.append(v)
    return out


def _release(source="model", *, version="2026.08.1", released_at="2026-08-03"):
    return {
        "id": 7,
        "version": version,
        "released_at": released_at,
        "note": {
            "headline": "Panel yenilendi",
            "source": source,
            "body": {
                "added": [{"text": "Yeni rozet eklendi", "shas": [SHA_A]}],
                "fixed": [{"text": "Hiza düzeltildi", "shas": [SHA_B]}],
                "improved": [],
            },
        },
        "changes": [
            {"change_type": "feat", "summary": f"yeni rozet {MARKER}", "commit_sha": SHA_A},
            {"change_type": "fix", "summary": "hiza", "commit_sha": SHA_B},
            {"change_type": "chore", "summary": "bağımlılık", "commit_sha": "cccccccccccc"},
        ],
        "services": [],
    }


# --- group_changes (eski _split_changes testinin yerine) ------------------

def test_visible_change_filter_hides_chore():
    groups, internal = vv.group_changes(_release()["changes"])
    assert [c["summary"] for c in groups["feat"]] == [f"yeni rozet {MARKER}"]
    assert [c["summary"] for c in groups["fix"]] == ["hiza"]
    assert internal == 1


def test_group_changes_tolerates_missing_type():
    groups, internal = vv.group_changes([{"summary": "x"}])
    assert internal == 1
    assert all(not v for v in groups.values())


# --- not okuma ------------------------------------------------------------

def test_panel_never_reads_draft_body():
    rel = _release()
    rel["note"]["draft_body"] = {"added": [{"text": "TASLAK", "shas": [SHA_A]}]}
    text = " ".join(_flatten(vv.hero_card(rel)))
    assert "TASLAK" not in text


def test_model_note_bullets_appear_in_the_card_body():
    text = " ".join(_flatten(vv.headline_block(_release("model"))))
    assert "Yeni rozet eklendi" in text
    assert "Hiza düzeltildi" in text


def test_auto_note_shows_a_code_written_summary_instead_of_bullets():
    block = " ".join(_flatten(vv.headline_block(_release("auto"))))
    assert "otomatik özet" in block.lower()
    assert "Yeni rozet eklendi" not in block


def test_raw_commit_subject_never_reaches_the_card_body():
    for source in ("model", "auto"):
        block = " ".join(_flatten(vv.headline_block(_release(source))))
        assert MARKER not in block, f"{source} kartının gövdesinde ham commit subject'i var"


def test_raw_commit_subject_lives_in_the_technical_section():
    assert MARKER in " ".join(_flatten(vv.technical_section(_release("auto"))))


def test_missing_note_falls_back_to_a_summary_line():
    rel = _release()
    rel["note"] = None
    text = " ".join(_flatten(vv.headline_block(rel)))
    assert MARKER not in text
    assert text.strip() != ""


# --- sayılar kodda hesaplanır --------------------------------------------

def test_bucket_counts_are_computed_from_the_body():
    counts = vv.bucket_counts(_release()["note"]["body"])
    assert counts == {"added": 1, "fixed": 1, "improved": 0}


def test_auto_summary_line_reports_counts_in_turkish():
    line = vv.auto_summary_line(_release()["note"]["body"])
    assert "1 yenilik" in line
    assert "1 düzeltme" in line
    assert "iyileştirme" not in line


def test_auto_summary_line_handles_empty_note():
    assert vv.auto_summary_line({"added": [], "fixed": [], "improved": []}).strip() != ""


# --- "Yayında" rozeti -----------------------------------------------------

def test_live_version_comes_from_the_newest_deployment():
    live = vv.resolve_live_version(
        [{"version": "2026.08.2"}, {"version": "2026.08.1"}],
        [
            {"version": "2026.08.1", "started_at": "2026-08-01T10:00:00"},
            {"version": "2026.08.2", "started_at": "2026-08-03T10:00:00"},
        ],
    )
    assert live == "2026.08.2"


def test_live_version_falls_back_to_the_newest_release():
    assert vv.resolve_live_version([{"version": "2026.08.2"}], []) == "2026.08.2"


def test_is_live_ignores_surrounding_whitespace():
    assert vv.is_live({"version": " 2026.08.2 "}, "2026.08.2") is True


def test_is_live_is_false_when_no_live_version_known():
    assert vv.is_live({"version": "2026.08.2"}, None) is False


# --- arama ve ay ayracı ---------------------------------------------------

def test_search_matches_version_headline_and_bullets():
    rel = _release()
    assert vv.matches_search(rel, "2026.08") is True
    assert vv.matches_search(rel, "panel") is True
    assert vv.matches_search(rel, "hiza") is True
    assert vv.matches_search(rel, "kesinlikle-yok") is False


def test_search_is_case_insensitive_and_empty_term_matches_all():
    assert vv.matches_search(_release(), "PANEL") is True
    assert vv.matches_search(_release(), "") is True


def test_month_label_is_turkish():
    assert vv.month_label("2026-08-03") == "Ağustos 2026"


def test_month_label_tolerates_garbage():
    assert vv.month_label("") == "Tarihsiz"


# --- tema renkleri --------------------------------------------------------

def test_no_hardcoded_hex_colours_remain():
    for module in (vv, page):
        src = Path(module.__file__).read_text(encoding="utf-8")
        assert not re.search(r"#[0-9A-Fa-f]{6}\b", src), f"{module.__name__} içinde sabit hex renk var"


# --- sayfa iskeleti -------------------------------------------------------

def test_build_layout_filters_by_search_query():
    releases = [_release(version="2026.08.2"), _release(version="2026.07.1", released_at="2026-07-01")]
    with patch.object(page.admin_client, "list_platform_releases", lambda: releases), \
         patch.object(page.admin_client, "get_current_versions", lambda: []):
        text = " ".join(_flatten(page.build_layout("?q=2026.07")))
    assert "2026.07.1" in text
    assert "2026.08.2" not in text


def test_build_layout_shows_empty_state_without_releases():
    with patch.object(page.admin_client, "list_platform_releases", lambda: []), \
         patch.object(page.admin_client, "get_current_versions", lambda: []):
        text = " ".join(_flatten(page.build_layout()))
    assert "Henüz sürüm geçmişi yok" in text
