"""release_notes saf fonksiyonları — DB yok, ağ yok."""

from __future__ import annotations

from datetime import datetime, timezone

from src.services import release_notes as rn

SHA_A = "aaaaaaaaaaaa"
SHA_B = "bbbbbbbbbbbb"
ALLOWED = {SHA_A, SHA_B}


def _empty() -> dict:
    return {"added": [], "fixed": [], "improved": []}


# --- parse_commit_subject -------------------------------------------------

def test_parse_strips_conventional_prefix_and_scope():
    assert rn.parse_commit_subject("feat(panel): yeni rozet") == ("feat", "yeni rozet", "panel")


def test_parse_handles_breaking_marker():
    assert rn.parse_commit_subject("fix!: kritik hata") == ("fix", "kritik hata", None)


def test_parse_unknown_prefix_becomes_other():
    assert rn.parse_commit_subject("merge branch main") == ("other", "merge branch main", None)


# --- trt_date / calver ----------------------------------------------------

def test_trt_date_rolls_over_at_istanbul_midnight():
    # 2026-08-03 21:30 UTC = 2026-08-04 00:30 TRT
    dt = datetime(2026, 8, 3, 21, 30, tzinfo=timezone.utc)
    assert rn.trt_date(dt).isoformat() == "2026-08-04"


def test_calver_pads_month():
    assert rn.calver(rn.trt_date(datetime(2026, 8, 3, 9, 0, tzinfo=timezone.utc)), 2) == "2026.08.2"


# --- fingerprint ----------------------------------------------------------

def test_fingerprint_is_order_independent():
    a = [{"commit_sha": SHA_A}, {"commit_sha": SHA_B}]
    b = [{"commit_sha": SHA_B}, {"commit_sha": SHA_A}]
    assert rn.fingerprint(a) == rn.fingerprint(b)


def test_fingerprint_changes_with_new_commit():
    a = [{"commit_sha": SHA_A}]
    b = [{"commit_sha": SHA_A}, {"commit_sha": SHA_B}]
    assert rn.fingerprint(a) != rn.fingerprint(b)


# --- deterministic_note ---------------------------------------------------

def test_deterministic_note_maps_types_to_buckets():
    note = rn.deterministic_note(
        [
            {"change_type": "feat", "summary": "yeni panel", "commit_sha": SHA_A},
            {"change_type": "fix", "summary": "rozet düzeltildi", "commit_sha": SHA_B},
        ]
    )
    assert note["added"][0]["text"] == "Yeni panel"
    assert note["added"][0]["shas"] == [SHA_A]
    assert note["fixed"][0]["text"] == "Rozet düzeltildi"
    assert note["improved"] == []


def test_deterministic_note_drops_internal_types():
    note = rn.deterministic_note([{"change_type": "chore", "summary": "bağımlılık", "commit_sha": SHA_A}])
    assert note == _empty()


def test_deterministic_note_never_raises_on_garbage():
    assert rn.deterministic_note([{}, {"change_type": None}, {"summary": ""}]) == _empty()


# --- validate_note --------------------------------------------------------

def test_validate_drops_unknown_buckets():
    out = rn.validate_note(
        {"added": [{"text": "iyi", "shas": [SHA_A]}], "removed": [{"text": "kötü", "shas": [SHA_B]}]},
        ALLOWED,
    )
    assert "removed" not in out
    assert len(out["added"]) == 1


def test_validate_drops_unknown_sha():
    out = rn.validate_note({"added": [{"text": "uydurma", "shas": ["cccccccccccc"]}]}, ALLOWED)
    assert out == _empty()


def test_validate_gives_a_sha_to_the_first_bullet_only():
    out = rn.validate_note(
        {
            "added": [{"text": "birinci", "shas": [SHA_A]}, {"text": "ikinci", "shas": [SHA_A]}],
        },
        ALLOWED,
    )
    assert [b["text"] for b in out["added"]] == ["birinci"]


def test_validate_caps_bullet_count_at_commit_count():
    raw = {"added": [{"text": f"madde {i}", "shas": [SHA_A, SHA_B]} for i in range(10)]}
    out = rn.validate_note(raw, ALLOWED)
    total = sum(len(out[b]) for b in rn.BUCKETS)
    assert total <= len(ALLOWED)


def test_validate_drops_overlong_text():
    out = rn.validate_note({"added": [{"text": "x" * 201, "shas": [SHA_A]}]}, ALLOWED)
    assert out == _empty()


def test_validate_cleans_sha_tokens_from_text():
    out = rn.validate_note({"added": [{"text": f"yeni panel ({SHA_A})", "shas": [SHA_A]}]}, ALLOWED)
    assert SHA_A not in out["added"][0]["text"]
    assert "yeni panel" in out["added"][0]["text"]


def test_validate_cleans_conventional_prefix_from_text():
    out = rn.validate_note({"added": [{"text": "feat(panel): yeni rozet", "shas": [SHA_A]}]}, ALLOWED)
    assert out["added"][0]["text"] == "yeni rozet"


def test_validate_drops_bullet_without_sha():
    out = rn.validate_note({"added": [{"text": "kaynaksız iddia", "shas": []}]}, ALLOWED)
    assert out == _empty()


def test_validate_returns_empty_on_non_dict():
    assert rn.validate_note("çöp", ALLOWED) == _empty()
    assert rn.validate_note(None, ALLOWED) == _empty()


def test_validate_survives_malformed_items():
    out = rn.validate_note({"added": ["düz metin", 42, {"text": "iyi", "shas": [SHA_A]}]}, ALLOWED)
    assert [b["text"] for b in out["added"]] == ["iyi"]


# --- build_payload --------------------------------------------------------

def test_build_payload_carries_only_allowed_fields():
    payload = rn.build_payload(
        {"version": "2026.08.1", "released_at": "2026-08-03"},
        [{"change_type": "feat", "summary": "yeni panel", "commit_sha": SHA_A, "scope": "panel"}],
    )
    assert payload["version"] == "2026.08.1"
    assert payload["changes"][0] == {
        "change_type": "feat",
        "summary": "yeni panel",
        "sha": SHA_A,
        "scope": "panel",
    }
