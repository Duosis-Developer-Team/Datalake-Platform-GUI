"""Frontend chatbot context-extraction tests."""

from src.components.chatbot import extract_context, extract_datacenter


def test_extract_datacenter_from_datacenter_path():
    assert extract_datacenter("/datacenter/DC13") == "DC13"


def test_extract_datacenter_from_dc_detail_path():
    assert extract_datacenter("/dc-detail/DC13") == "DC13"


def test_extract_datacenter_handles_other_codes():
    assert extract_datacenter("/dc/AZ2") == "AZ2"


def test_extract_datacenter_none_on_list_page():
    assert extract_datacenter("/datacenters") is None
    assert extract_datacenter("/") is None


def test_extract_context_full_shape():
    ctx = extract_context("/datacenter/DC13", "?x=1", {"preset": "7d"}, "Boyner")
    assert ctx["selected_datacenter"] == "DC13"
    assert ctx["selected_customer"] == "Boyner"
    assert ctx["time_range"] == {"preset": "7d"}
    assert ctx["pathname"] == "/datacenter/DC13"
    assert ctx["page_title"] == "Datacenter DC13"


def test_extract_context_safe_defaults():
    ctx = extract_context(None, None, None, None)
    assert ctx["pathname"] == "/"
    assert ctx["selected_datacenter"] is None
    assert ctx["selected_customer"] is None
    assert ctx["time_range"] == {}
