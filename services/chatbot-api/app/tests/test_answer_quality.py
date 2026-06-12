"""Tests for narrative-first answer quality detection."""

from __future__ import annotations

from app.services.answer_quality import is_narrative_incomplete


def test_table_only_is_incomplete():
    table = "| A | B |\n|---|---|\n| 1 | 2 |"
    assert is_narrative_incomplete(table) is True


def test_table_first_is_incomplete():
    answer = "| VM | CPU |\n|---|---|\n| x | 90 |\n\n**Sonuç:** yüksek"
    assert is_narrative_incomplete(answer) is True


def test_missing_analiz_is_incomplete():
    assert is_narrative_incomplete("**Sonuç:** DC13 yoğun.") is True


def test_missing_sonuc_is_incomplete():
    assert is_narrative_incomplete("**Analiz:** kontrol edildi.") is True


def test_good_narrative_is_complete():
    answer = (
        "**Analiz:** DC13 VM CPU verisi incelendi; en yüksek tüketim %85 seviyesinde.\n\n"
        "**Sonuç:** Son 7 günde VM-A en yoğun kaynak.\n\n"
        "**Risk seviyesi:** medium"
    )
    assert is_narrative_incomplete(answer) is False


def test_narrative_with_appendix_table_is_complete():
    answer = (
        "**Analiz:** Top 5 VM incelendi; VM-A sürekli yüksek.\n\n"
        "**Sonuç:** VM-A, VM-B ve VM-C öncelikli.\n\n"
        "| # | VM | CPU % |\n|---|-----|------:|\n| 1 | A | 85 |\n| 2 | B | 80 |"
    )
    assert is_narrative_incomplete(answer) is False


def test_table_dominated_without_sections_is_incomplete():
    lines = [f"| {i} | x | {i} |" for i in range(10)]
    lines += ["|---|---|---|", "| h | h | h |"]
    assert is_narrative_incomplete("\n".join(lines)) is True


def test_table_dominated_with_sections_is_acceptable():
    lines = ["**Analiz:** kısa", "**Sonuç:** kısa"]
    lines += [f"| {i} | x | {i} |" for i in range(10)]
    lines += ["|---|---|---|", "| h | h | h |"]
    assert is_narrative_incomplete("\n".join(lines)) is False
