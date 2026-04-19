"""Trace Dash callback execution time as child spans."""

from __future__ import annotations

import functools
from typing import Any, Callable, TypeVar

from opentelemetry import trace

F = TypeVar("F", bound=Callable[..., Any])
_tracer = trace.get_tracer(__name__)


def trace_dash_callback(name: str) -> Callable[[F], F]:
    """
    Decorator for Dash callback functions. Place directly above the function, below @app.callback(...).

    Example::

        @app.callback(...)
        @trace_dash_callback("render_main_content")
        def render_main_content(...):
            ...
    """

    def decorator(fn: F) -> F:
        span_name = f"dash.callback.{name}"

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with _tracer.start_as_current_span(span_name):
                return fn(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
