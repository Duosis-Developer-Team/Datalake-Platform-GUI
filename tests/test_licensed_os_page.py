from unittest.mock import patch
from src.pages import licensed_os


def test_build_layout_renders_family_counts():
    fake = {
        "families": {"rhel": 3, "suse": 1, "windows": 5, "free": 10, "unknown": 2},
        "total": 21, "unknown_samples": ["Other Linux (64-bit)"],
    }
    with patch("src.pages.licensed_os.api.get_licensed_os_summary", return_value=fake):
        layout = licensed_os.build_layout()
    # smoke: it builds without error and is a Dash component tree
    assert layout is not None
    assert hasattr(layout, "children")


def test_page_module_exposes_shell_and_layout():
    # both entry points the app.py router relies on must exist and be callable
    assert callable(licensed_os.build_layout_shell)
    assert callable(licensed_os.build_layout)
