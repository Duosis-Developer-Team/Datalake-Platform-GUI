"""Security helpers: in-memory rate limiting + forbidden-intent detection.

These are defence-in-depth controls that run *before* and *independently of* the
LLM, so the tool/data layer enforces safety even if a prompt tries to talk the
model into something forbidden (CTO pack 06_SECURITY_RBAC_AND_AUDIT).
"""

from __future__ import annotations

import re
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass

# --------------------------------------------------------------------------- #
# Rate limiting (per-user sliding window, in-memory MVP)
# --------------------------------------------------------------------------- #


@dataclass
class RateLimitDecision:
    allowed: bool
    reason: str = ""


class RateLimiter:
    """Sliding-window limiter keyed by user identity.

    MVP uses process-local memory; a later sprint can swap in Redis counters
    (Redis is already in the stack) without changing the call site.
    """

    def __init__(self, per_minute: int, per_hour: int) -> None:
        self.per_minute = per_minute
        self.per_hour = per_hour
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, now: float | None = None) -> RateLimitDecision:
        now = time.monotonic() if now is None else now
        with self._lock:
            dq = self._hits[key]
            # Drop entries older than 1 hour.
            cutoff_hour = now - 3600.0
            while dq and dq[0] < cutoff_hour:
                dq.popleft()
            last_minute = sum(1 for t in dq if t >= now - 60.0)
            if last_minute >= self.per_minute:
                return RateLimitDecision(False, "minute")
            if len(dq) >= self.per_hour:
                return RateLimitDecision(False, "hour")
            dq.append(now)
            return RateLimitDecision(True)


# --------------------------------------------------------------------------- #
# Forbidden-intent detection (hard guard, independent of the LLM)
# --------------------------------------------------------------------------- #

# Requests for secrets / credentials.
_SECRET_INTENT = re.compile(
    r"(api[_\s-]?key|api[_\s-]?token|bulutistan_llm_api_key|secret[_\s-]?key|"
    r"bearer\s+token|jwt\s+secret|db[_\s-]?pass(word)?|şifre|parola|"
    r"password\s*hash|ldap.*bind|environment\s+(variable|değişken)|env\s+var)",
    re.IGNORECASE,
)
# Requests to mutate data / run write SQL. Two signals are required to avoid
# false positives on benign words (e.g. "son update ne zaman"): a destructive
# verb AND a data/SQL context — OR an unambiguous SQL statement fragment.
_WRITE_VERB = re.compile(
    r"\b(drop|delete|truncate|update|insert|alter|create|grant|revoke)\b",
    re.IGNORECASE,
)
_SQL_CONTEXT = re.compile(
    r"(\btablo|\btable\b|\bsql\b|\bquery\b|\bdatabase\b|\bveritaban|\bschema\b|"
    r"\bcolumn\b|\bkolon\b|\bfrom\s+\w+|\binto\s+\w+|\bset\s+\w+\s*=)",
    re.IGNORECASE,
)
_HARD_SQL = re.compile(
    r"\b(drop\s+table|delete\s+from|truncate\s+table|insert\s+into|"
    r"update\s+\w+\s+set|alter\s+table|create\s+table|grant\s+\w+|revoke\s+\w+)",
    re.IGNORECASE,
)
# Classic prompt-injection openers.
_INJECTION = re.compile(
    r"(ignore\s+(all\s+)?(previous|prior|above)\s+instructions|"
    r"disregard\s+(all\s+)?(previous|prior|above)|"
    r"önceki\s+talimatları\s+(yok\s+say|unut)|"
    r"reveal\s+(your\s+|the\s+)?(system\s+)?prompt|"
    r"show\s+(me\s+)?(your\s+|the\s+)?(system\s+)?prompt|"
    r"print\s+your\s+(api|secret|token))",
    re.IGNORECASE,
)


def _is_write_intent(text: str) -> bool:
    if _HARD_SQL.search(text):
        return True
    return bool(_WRITE_VERB.search(text) and _SQL_CONTEXT.search(text))


@dataclass
class IntentFlags:
    wants_secret: bool = False
    wants_write: bool = False
    injection: bool = False

    @property
    def is_forbidden(self) -> bool:
        return self.wants_secret or self.wants_write or self.injection


def classify_intent(message: str) -> IntentFlags:
    text = message or ""
    return IntentFlags(
        wants_secret=bool(_SECRET_INTENT.search(text)),
        wants_write=_is_write_intent(text),
        injection=bool(_INJECTION.search(text)),
    )
