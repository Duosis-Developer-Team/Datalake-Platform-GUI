"""Secret redaction for logs/audit (CTO pack 06_SECURITY_RBAC_AND_AUDIT).

``redact_text`` scrubs anything that looks like a credential before it can reach
a log line, an audit record, or the LLM context. It is intentionally aggressive:
false positives (a redacted token) are far cheaper than a leaked secret.
"""

from __future__ import annotations

import re

_REDACTED = "[REDACTED]"

_PATTERNS: list[re.Pattern[str]] = [
    # OpenAI / Bulutistan style project keys: sk-proj-..., sk-..., Sk-... (any case)
    re.compile(r"(?i)sk-[A-Za-z0-9_\-]{8,}"),
    # Authorization: Bearer <token>
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{10,}"),
    # JWT (three base64url segments)
    re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"),
    # key/value secrets: password=..., api_key: ..., token => ...
    re.compile(
        r"(?i)\b(pass(word)?|api[_-]?key|secret|token|bind[_-]?password)\b\s*[:=]\s*\S+"
    ),
    # Postgres / generic DB connection strings with embedded credentials
    re.compile(r"(?i)(postgres(ql)?|mysql|redis|amqp)://[^\s'\"]+"),
]


def redact_text(value: str | None) -> str:
    """Return ``value`` with credential-like substrings replaced by ``[REDACTED]``."""
    if not value:
        return ""
    out = value
    for pat in _PATTERNS:
        out = pat.sub(_REDACTED, out)
    return out


def redact_mapping(data: dict | None) -> dict:
    """Shallow-redact obvious secret keys in a dict (e.g. for safe log dumps)."""
    if not data:
        return {}
    safe: dict = {}
    sensitive = ("pass", "secret", "token", "key", "authorization", "bind_password")
    for k, v in data.items():
        if any(s in str(k).lower() for s in sensitive):
            safe[k] = _REDACTED
        elif isinstance(v, str):
            safe[k] = redact_text(v)
        else:
            safe[k] = v
    return safe
