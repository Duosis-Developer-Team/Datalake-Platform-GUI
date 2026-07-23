"""The HMDL/Automation-Health sub-nav tabs carry a red staleness count badge."""

from unittest.mock import patch

from src.pages.settings import shell

_BADGE_ID = "hmdl-staleness-badge"


@patch("src.services.api_client.get_hmdl_automation_health")
@patch("src.auth.permission_service.can_view")
def test_sub_nav_shows_alert_badge_on_hmdl_tabs(mock_can_view, mock_ah):
    mock_can_view.return_value = True
    mock_ah.return_value = {"counts": {"alert": 3, "stale": 1, "dead": 2}}
    nav = shell._sub_nav(1, "/administration/integrations/hmdl/automation-health")
    rendered = str(nav)
    assert _BADGE_ID in rendered  # staleness badge is present
    assert "'children': 3" in rendered or "children=3" in rendered  # shows the count


@patch("src.services.api_client.get_hmdl_automation_health")
@patch("src.auth.permission_service.can_view")
def test_sub_nav_no_badge_when_no_alert(mock_can_view, mock_ah):
    mock_can_view.return_value = True
    mock_ah.return_value = {"counts": {"alert": 0, "stale": 0, "dead": 0}}
    nav = shell._sub_nav(1, "/administration/integrations/hmdl")
    assert nav is not None  # nav still renders
    assert _BADGE_ID not in str(nav)  # but no badge when nothing is stale
