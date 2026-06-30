"""Customer View manager / customer perspective helpers."""
from __future__ import annotations

PERSPECTIVE_MANAGER = "manager"
PERSPECTIVE_CUSTOMER = "customer"

PERM_PERSPECTIVE_MANAGER = "sub:customer:perspective:manager"
PERM_PERSPECTIVE_CUSTOMER = "sub:customer:perspective:customer"


def perspective_access(visible_sections) -> dict[str, bool]:
    """Resolve which page perspectives the user may view."""
    if visible_sections is None:
        return {"manager": True, "customer": True}
    vs = set(visible_sections)
    return {
        "manager": PERM_PERSPECTIVE_MANAGER in vs,
        "customer": PERM_PERSPECTIVE_CUSTOMER in vs,
    }


def show_perspective_switch(access: dict[str, bool]) -> bool:
    return bool(access.get("manager") and access.get("customer"))


def default_perspective(access: dict[str, bool]) -> str:
    if access.get("manager"):
        return PERSPECTIVE_MANAGER
    return PERSPECTIVE_CUSTOMER


def effective_perspective(requested: str | None, access: dict[str, bool]) -> str:
    """Return a perspective the user is allowed to see."""
    if not access.get("manager") and not access.get("customer"):
        return PERSPECTIVE_MANAGER
    choice = requested or default_perspective(access)
    if choice == PERSPECTIVE_CUSTOMER and access.get("customer"):
        return PERSPECTIVE_CUSTOMER
    if choice == PERSPECTIVE_MANAGER and access.get("manager"):
        return PERSPECTIVE_MANAGER
    return default_perspective(access)
