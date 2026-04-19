"""Custom spans for authentication events (child spans under the Flask request span)."""

from __future__ import annotations

from typing import Optional

from opentelemetry import trace

_tracer = trace.get_tracer(__name__)


def record_login_attempt(
    *,
    outcome: str,
    method: str,
    username: Optional[str] = None,
) -> None:
    """
    Record a login attempt outcome.

    outcome: success | failure
    method: local | ldap
    """
    with _tracer.start_as_current_span("auth.login") as span:
        span.set_attribute("auth.event", "login")
        span.set_attribute("auth.outcome", outcome)
        span.set_attribute("auth.method", method)
        if username:
            span.set_attribute("auth.username", username[:128])


def record_logout() -> None:
    with _tracer.start_as_current_span("auth.logout") as span:
        span.set_attribute("auth.event", "logout")
