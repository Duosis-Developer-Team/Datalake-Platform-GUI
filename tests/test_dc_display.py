from src.utils.dc_display import format_dc_display_name


def test_format_dc_display_name_with_description():
    assert format_dc_display_name("DC13", "Equinix IL2 DC") == "DC13 - Equinix IL2 DC"


def test_format_dc_display_name_empty_description():
    assert format_dc_display_name("DC13", "") == "DC13"
    assert format_dc_display_name("DC13", None) == "DC13"


def test_format_dc_display_name_same_as_name():
    assert format_dc_display_name("DC13", "DC13") == "DC13"


def test_format_dc_display_name_casefold_duplicate():
    assert format_dc_display_name("DC13", "dc13") == "DC13"
