from datetime import datetime, timedelta, timezone

from app.core.time_filter import TimeFilter


def _today():
    return datetime.now(timezone.utc).date()


def test_preset_7d_returns_last_7_days():
    tf = TimeFilter(start=None, end=None, preset="7d")
    result = tf.to_dict()
    today = _today()
    assert result["end"] == today.isoformat()
    assert result["start"] == (today - timedelta(days=6)).isoformat()
    assert result["preset"] == "7d"


def test_preset_30d_returns_last_30_days():
    tf = TimeFilter(start=None, end=None, preset="30d")
    result = tf.to_dict()
    today = _today()
    assert result["end"] == today.isoformat()
    assert result["start"] == (today - timedelta(days=29)).isoformat()
    assert result["preset"] == "30d"


def test_preset_1d_returns_today():
    tf = TimeFilter(start=None, end=None, preset="1d")
    result = tf.to_dict()
    today = _today()
    assert result["start"] == today.isoformat()
    assert result["end"] == today.isoformat()
    assert result["preset"] == "1d"


def test_custom_start_end_overrides_preset():
    tf = TimeFilter(start="2026-03-01", end="2026-03-10", preset="7d")
    result = tf.to_dict()
    assert result["start"] == "2026-03-01"
    assert result["end"] == "2026-03-10"
    assert result["preset"] == "custom"


def test_custom_start_end_without_preset():
    tf = TimeFilter(start="2026-01-01", end="2026-01-31", preset=None)
    result = tf.to_dict()
    assert result["start"] == "2026-01-01"
    assert result["end"] == "2026-01-31"
    assert result["preset"] == "custom"


def test_no_params_defaults_to_7d():
    tf = TimeFilter(start=None, end=None, preset=None)
    result = tf.to_dict()
    today = _today()
    assert result["end"] == today.isoformat()
    assert result["start"] == (today - timedelta(days=6)).isoformat()
    assert result["preset"] == "7d"


def test_invalid_preset_falls_back_to_7d():
    tf = TimeFilter(start=None, end=None, preset="invalid_value")
    result = tf.to_dict()
    today = _today()
    assert result["end"] == today.isoformat()
    assert result["start"] == (today - timedelta(days=6)).isoformat()
    assert result["preset"] == "invalid_value"


def test_to_dict_always_returns_start_end_preset_keys():
    cases = [
        {"start": None, "end": None, "preset": "7d"},
        {"start": None, "end": None, "preset": "30d"},
        {"start": None, "end": None, "preset": "1d"},
        {"start": "2026-03-01", "end": "2026-03-10", "preset": None},
        {"start": None, "end": None, "preset": None},
        {"start": None, "end": None, "preset": "invalid"},
    ]
    for kwargs in cases:
        result = TimeFilter(**kwargs).to_dict()
        assert "start" in result
        assert "end" in result
        assert "preset" in result
        assert isinstance(result["start"], str)
        assert isinstance(result["end"], str)
        assert isinstance(result["preset"], str)


def test_partial_start_without_end_falls_back_to_default():
    tf = TimeFilter(start="2026-03-01", end=None, preset=None)
    result = tf.to_dict()
    assert result["preset"] == "7d"


def test_partial_end_without_start_falls_back_to_default():
    tf = TimeFilter(start=None, end="2026-03-10", preset=None)
    result = tf.to_dict()
    assert result["preset"] == "7d"


def test_preset_7d_start_is_6_days_before_end():
    tf = TimeFilter(start=None, end=None, preset="7d")
    result = tf.to_dict()
    start = datetime.fromisoformat(result["start"]).date()
    end = datetime.fromisoformat(result["end"]).date()
    assert (end - start).days == 6


def test_preset_30d_start_is_29_days_before_end():
    tf = TimeFilter(start=None, end=None, preset="30d")
    result = tf.to_dict()
    start = datetime.fromisoformat(result["start"]).date()
    end = datetime.fromisoformat(result["end"]).date()
    assert (end - start).days == 29
