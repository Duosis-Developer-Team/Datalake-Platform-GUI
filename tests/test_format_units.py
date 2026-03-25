import math

from src.utils.format_units import (
    smart_bytes_1024,
    smart_frequency_hz,
    smart_storage,
    smart_memory,
    smart_cpu,
    smart_bytes,
)
from src.utils.format_units import parse_storage_string


def test_smart_bytes_1024_thresholds():
    assert smart_bytes_1024(0) == "0.00 B"
    assert smart_bytes_1024(1023) == "1023.00 B"
    assert smart_bytes_1024(1024) == "1.00 KB"
    assert smart_bytes_1024(1024**2) == "1.00 MB"
    assert smart_bytes_1024(1024**3) == "1.00 GB"


def test_smart_bytes_1024_negative_and_none():
    assert smart_bytes_1024(None) == "0.00 B"
    assert smart_bytes_1024(-1024) == "-1.00 KB"


def test_smart_bytes_alias():
    value = 5 * 1024**3
    assert smart_bytes(value) == smart_bytes_1024(value)


def test_smart_frequency_hz_thresholds():
    assert smart_frequency_hz(0) == "0.00 Hz"
    assert smart_frequency_hz(999) == "999.00 Hz"
    assert smart_frequency_hz(1000) == "1.00 kHz"
    assert smart_frequency_hz(1_000_000) == "1.00 MHz"
    assert smart_frequency_hz(1_000_000_000) == "1.00 GHz"
    assert smart_frequency_hz(1_000_000_000_000) == "1.00 THz"


def test_smart_frequency_hz_negative_and_none():
    assert smart_frequency_hz(None) == "0.00 Hz"
    assert smart_frequency_hz(-1000) == "-1.00 kHz"


def test_smart_cpu_uses_frequency_helper():
    assert smart_cpu(1.5) == "1.50 GHz"
    assert smart_cpu(0.5) == "500.00 MHz"
    assert smart_cpu(None) == "0.00 GHz"


def test_smart_storage_and_memory_from_gb():
    # 1 GB should stay 1.00 GB
    assert smart_storage(1) == "1.00 GB"
    assert smart_memory(1) == "1.00 GB"

    # 1024 GB should become 1.00 TB
    assert smart_storage(1024) == "1.00 TB"
    assert smart_memory(1024) == "1.00 TB"


def test_parse_storage_string_tb_to_gb():
    assert math.isclose(parse_storage_string("110.00 TB"), 110.00 * 1024, rel_tol=1e-9)


def test_parse_storage_string_gb_to_gb():
    assert math.isclose(parse_storage_string("1 GB"), 1.0, rel_tol=1e-9)


def test_parse_storage_string_mb_to_gb():
    assert math.isclose(parse_storage_string("500 MB"), 500 / 1024, rel_tol=1e-9)


def test_parse_storage_string_invalid_returns_zero():
    assert parse_storage_string("N/A") == 0.0
    assert parse_storage_string("unknown") == 0.0


def test_parse_storage_string_none_returns_zero():
    assert parse_storage_string(None) == 0.0

