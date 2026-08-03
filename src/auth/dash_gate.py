"""Authorization gate for Dash's callback transport.

`POST /_dash-update-component` dispatches *every* server callback in the app,
page callbacks included, and those return real inventory rows. It cannot simply
redirect to /login the way a normal route does: the login form itself is the
`main-content.children` callback's return value, so the shell must be able to
run callbacks before anyone is logged in.

The `output` field in the request body is what selects which callback the server
runs, so it is a sound authorization key — a caller cannot reach a page callback
without naming its output. That gives us the rule:

    unauthenticated requests may only target components of the static app shell.

The shell id set is derived from `app.layout` at boot (see
`set_shell_component_ids`) rather than hand-maintained, so a component added to
the shell is allowed automatically and a component injected by a page — which
only exists in the DOM *after* `main-content.children` has already been
authorized — is denied automatically.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

logger = logging.getLogger(__name__)

# Populated once from app.layout at boot. None means "not registered yet"; the
# gate stays inert in that state so a wiring mistake cannot lock the whole app
# out of its own callbacks.
_shell_component_ids: set[str] | None = None


def set_shell_component_ids(ids: Iterable[str] | None) -> None:
    """Register the app-shell component ids the gate treats as public."""
    global _shell_component_ids
    _shell_component_ids = None if ids is None else set(ids)


def get_shell_component_ids() -> set[str] | None:
    return _shell_component_ids


def collect_component_ids(node: Any, _seen: set[int] | None = None) -> set[str]:
    """Walk a Dash layout tree and return every string component id in it.

    Components can hold other components in props other than `children`
    (`dcc.Loading`, `dmc.Modal`, tab panels), so every prop is traversed, not
    just the child list. Dict ids (pattern-matching) are skipped: those belong
    to page content by construction.
    """
    if _seen is None:
        _seen = set()

    if isinstance(node, (list, tuple)):
        found: set[str] = set()
        for item in node:
            found |= collect_component_ids(item, _seen)
        return found

    if not _is_dash_component(node):
        return set()

    if id(node) in _seen:
        return set()
    _seen.add(id(node))

    found = set()
    node_id = getattr(node, "id", None)
    if isinstance(node_id, str) and node_id:
        found.add(node_id)

    for prop in getattr(node, "_prop_names", None) or ():
        if prop == "id":
            continue
        try:
            value = getattr(node, prop)
        except AttributeError:
            continue
        found |= collect_component_ids(value, _seen)

    return found


def _is_dash_component(node: Any) -> bool:
    return hasattr(node, "_prop_names") and hasattr(node, "_type")


def split_output_targets(output: str | None) -> list[str]:
    """Split a callback `output` field into its individual `<id>.<prop>` targets.

    Dash encodes a single output as `"id.prop"` and a grouped output as
    `"..id.prop...id2.prop2.."`.
    """
    text = (output or "").strip()
    if not text:
        return []
    if text.startswith("..") and text.endswith(".."):
        body = text[2:-2]
        return [part for part in body.split("...") if part]
    return [text]


def target_component_id(target: str) -> str | None:
    """Return the component id of one `<id>.<prop>` target, or None if unparseable.

    Pattern-matching ids are JSON objects and are returned verbatim so they
    simply fail the shell-membership check (shell ids are always strings).
    """
    target = target.strip()
    if not target:
        return None
    if target.startswith("{"):
        close = target.rfind("}")
        return target[: close + 1] if close != -1 else None
    if "." not in target:
        return None
    return target.rsplit(".", 1)[0] or None


def output_component_ids(output: str | None) -> set[str]:
    """Every component id named by a callback `output` field.

    An unparseable target contributes nothing, so callers must compare against
    the target count rather than treating an empty set as "harmless".
    """
    ids = set()
    for target in split_output_targets(output):
        cid = target_component_id(target)
        if cid:
            ids.add(cid)
    return ids


def is_shell_only(output: str | None, shell_ids: Iterable[str]) -> bool:
    """True when every target of `output` is an app-shell component.

    A grouped output is allowed only if *all* of its targets are shell
    components — the callback behind it runs as a single unit, so one page
    target is enough to make the whole request privileged.
    """
    targets = split_output_targets(output)
    if not targets:
        return False

    shell = set(shell_ids)
    for target in targets:
        cid = target_component_id(target)
        if cid is None or cid not in shell:
            return False
    return True


def is_public_callback_request(body: Any) -> bool:
    """True when an unauthenticated caller may run the callback in `body`."""
    shell = _shell_component_ids
    if shell is None:
        # Shell ids were never registered — fail open rather than brick the app.
        logger.warning("dash gate: shell component ids not registered, allowing request")
        return True
    if not isinstance(body, dict):
        return False
    return is_shell_only(body.get("output"), shell)
