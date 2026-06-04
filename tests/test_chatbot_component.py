"""Frontend chatbot widget rendering tests."""

from src.components.chatbot import build_chatbot_shell

_REQUIRED_IDS = [
    "chatbot-fab",
    "chatbot-panel",
    "chatbot-close-button",
    "chatbot-messages",
    "chatbot-input",
    "chatbot-send-button",
    "chatbot-status",
]


def _collect_ids(component, found=None):
    if found is None:
        found = set()
    cid = getattr(component, "id", None)
    if isinstance(cid, str):
        found.add(cid)
    children = getattr(component, "children", None)
    if children is None:
        return found
    if isinstance(children, (list, tuple)):
        for child in children:
            _collect_ids(child, found)
    else:
        _collect_ids(children, found)
    return found


def test_shell_renders_required_ids():
    ids = _collect_ids(build_chatbot_shell())
    for needed in _REQUIRED_IDS:
        assert needed in ids, f"missing component id: {needed}"


def test_shell_contains_no_api_token_or_llm_url():
    rendered = str(build_chatbot_shell())
    assert "sk-" not in rendered
    assert "Bearer" not in rendered
    assert "api.bulutistan.ai" not in rendered
