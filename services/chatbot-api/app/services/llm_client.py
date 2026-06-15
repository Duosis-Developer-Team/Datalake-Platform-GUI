"""Bulutistan LLMaaS client (OpenAI-compatible) with fallback + friendly errors.

Design goals (CTO pack 01 / 03):
* base_url, api_key, model all from env (never hardcoded).
* primary model -> fallback model only on *recoverable* failures
  (model unavailable / bad request about model / transient 5xx).
* never fall back on auth errors.
* map provider exceptions to short, user-safe Turkish messages — no stack
  traces leak to the UI.

``openai`` is imported defensively so the module (and the unit tests that mock
``LLMClient.complete``) import cleanly even if the SDK is absent in a dev venv.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from app.config import settings

logger = logging.getLogger("chatbot-api.llm")

try:  # pragma: no cover - exercised only when openai is installed
    from openai import (
        APIConnectionError,
        APIError,
        APITimeoutError,
        AuthenticationError,
        BadRequestError,
        NotFoundError,
        OpenAI,
        RateLimitError,
    )

    _OPENAI_AVAILABLE = True
except Exception:  # pragma: no cover - dev venv without openai
    _OPENAI_AVAILABLE = False
    OpenAI = None  # type: ignore[assignment]

    class _OpenAIErr(Exception):
        ...

    APIConnectionError = APIError = APITimeoutError = AuthenticationError = (
        BadRequestError
    ) = NotFoundError = RateLimitError = _OpenAIErr  # type: ignore[misc,assignment]


# --------------------------------------------------------------------------- #
# Result / error types
# --------------------------------------------------------------------------- #


@dataclass
class ToolCallRequest:
    id: str
    name: str
    arguments: str


@dataclass
class LLMResult:
    answer: str
    model: str
    usage: Optional[dict[str, Any]] = None


@dataclass
class LLMResultWithTools:
    content: Optional[str]
    model: str
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    finish_reason: Optional[str] = None
    usage: Optional[dict[str, Any]] = None


@dataclass
class LLMError(Exception):
    """Raised for any non-recoverable LLM failure, carrying a UI-safe message."""

    error_type: str
    user_message: str
    detail: str = field(default="", repr=False)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.error_type}: {self.user_message}"


# User-safe Turkish messages (CTO pack 03 Error UX).
MSG_NOT_CONFIGURED = (
    "Chatbot servisi Bulutistan LLMaaS API token'ı ile yapılandırılmamış. Sistem "
    "yöneticisinin BULUTISTAN_LLM_API_KEY secret/env değerini ayarlaması gerekiyor."
)
# Note: the upstream may phrase a 401 as "Invalid or expired JWT token", but the
# credential we send is a Bulutistan LLMaaS *API token* (Authorization: Bearer
# <API_TOKEN>), not a user JWT. Our wording reflects that.
MSG_AUTH_FAILED = (
    "Bulutistan LLMaaS API token'ı doğrulanamadı (geçersiz, süresi dolmuş, iptal "
    "edilmiş veya yetkisiz olabilir). Sistem yöneticisinin BULUTISTAN_LLM_API_KEY "
    "değerini geçerli bir API token ile güncellemesi gerekiyor."
)
MSG_RATE_LIMIT = (
    "Şu anda AI servisi rate limit'e takıldı. Biraz sonra tekrar deneyebilirsin."
)
MSG_TIMEOUT = "AI servisi zamanında yanıt vermedi. Lütfen birkaç saniye sonra tekrar dene."
MSG_UPSTREAM = "AI servisinde geçici bir sorun oluştu. Lütfen biraz sonra tekrar dene."
MSG_BAD_REQUEST = "İstek AI servisi tarafından işlenemedi. Lütfen sorunu kısaltıp tekrar dene."


class LLMClient:
    """Thin wrapper over the OpenAI-compatible chat completions endpoint."""

    def __init__(self, settings_obj=settings) -> None:
        self.settings = settings_obj
        self._client = None  # lazy
        self._tools_support: Optional[bool] = None  # cached probe result

    # -- configuration ------------------------------------------------------ #

    @property
    def is_configured(self) -> bool:
        return self.settings.llm_configured

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not _OPENAI_AVAILABLE:  # pragma: no cover - defensive
            raise LLMError(
                "not_configured",
                MSG_UPSTREAM,
                "openai SDK not installed in this environment",
            )
        self._client = OpenAI(
            api_key=self.settings.bulutistan_llm_api_key,
            base_url=self.settings.bulutistan_llm_base_url,
            timeout=self.settings.chatbot_timeout_seconds,
            max_retries=self.settings.chatbot_max_retries,
        )
        return self._client

    # -- public API --------------------------------------------------------- #

    def complete(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResult:
        """Run a non-streaming chat completion, with one fallback-model attempt.

        Raises ``LLMError`` (with a UI-safe message) on any failure.
        """
        if not self.is_configured:
            raise LLMError("not_configured", MSG_NOT_CONFIGURED)

        primary = model or self.settings.chatbot_model
        fallback = self.settings.chatbot_fallback_model

        try:
            return self._call(primary, messages, max_tokens=max_tokens)
        except LLMError as exc:
            # Only retry on recoverable model/transient errors and only if a
            # *different* fallback model is configured.
            if exc.error_type in {"model_unavailable", "bad_request", "upstream", "empty"} and fallback and fallback != primary:
                logger.warning("Primary model '%s' failed (%s); trying fallback '%s'", primary, exc.error_type, fallback)
                try:
                    return self._call(fallback, messages, max_tokens=max_tokens)
                except LLMError:
                    raise
            raise

    def probe_tools_support(self) -> bool:
        """Return whether the provider accepts the ``tools`` parameter (cached)."""
        if self._tools_support is not None:
            return self._tools_support
        if not self.is_configured or not _OPENAI_AVAILABLE:
            self._tools_support = False
            return False
        dummy_tools = [
            {
                "type": "function",
                "function": {
                    "name": "ping_tool",
                    "description": "Connectivity probe",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        try:
            client = self._get_client()
            resp = client.chat.completions.create(
                model=self.settings.chatbot_model,
                messages=[{"role": "user", "content": "Reply with OK only."}],
                tools=dummy_tools,
                max_tokens=5,
                temperature=0,
                stream=False,
            )
            msg = resp.choices[0].message
            _ = msg.content or msg.tool_calls
            self._tools_support = True
        except BadRequestError as exc:
            detail = str(exc).lower()
            if "tool" in detail or "function" in detail:
                logger.info("LLM provider rejected tools parameter: %s", exc)
                self._tools_support = False
            else:
                # Bad request for another reason — assume tools may work in ReAct.
                self._tools_support = True
        except Exception as exc:
            logger.warning("tools support probe failed: %s", exc)
            self._tools_support = False
        return self._tools_support

    def complete_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResultWithTools:
        """Chat completion with optional function/tool calls."""
        if not self.is_configured:
            raise LLMError("not_configured", MSG_NOT_CONFIGURED)

        use_model = model or self.settings.chatbot_model
        return self._call_with_tools(use_model, messages, tools, max_tokens=max_tokens)

    # -- internals ---------------------------------------------------------- #

    def _call_with_tools(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: Optional[int] = None,
    ) -> LLMResultWithTools:
        client = self._get_client()
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools,
                temperature=self.settings.chatbot_temperature,
                max_tokens=max_tokens or self.settings.chatbot_max_tokens,
                top_p=self.settings.chatbot_top_p,
                stream=False,
            )
        except AuthenticationError as exc:
            raise LLMError("auth", MSG_AUTH_FAILED, str(exc)) from exc
        except RateLimitError as exc:
            raise LLMError("rate_limit", MSG_RATE_LIMIT, str(exc)) from exc
        except APITimeoutError as exc:
            raise LLMError("timeout", MSG_TIMEOUT, str(exc)) from exc
        except NotFoundError as exc:
            raise LLMError("model_unavailable", MSG_BAD_REQUEST, str(exc)) from exc
        except BadRequestError as exc:
            raise LLMError("bad_request", MSG_BAD_REQUEST, str(exc)) from exc
        except (APIConnectionError, APIError) as exc:
            raise LLMError("upstream", MSG_UPSTREAM, str(exc)) from exc
        except Exception as exc:  # pragma: no cover
            raise LLMError("upstream", MSG_UPSTREAM, str(exc)) from exc

        choice = resp.choices[0]
        msg = choice.message
        content = (msg.content or "").strip() or None
        tool_calls: list[ToolCallRequest] = []
        for tc in getattr(msg, "tool_calls", None) or []:
            fn = tc.function
            tool_calls.append(
                ToolCallRequest(
                    id=tc.id,
                    name=fn.name,
                    arguments=fn.arguments or "{}",
                )
            )

        usage = None
        try:
            if getattr(resp, "usage", None) is not None:
                usage = {
                    "prompt_tokens": resp.usage.prompt_tokens,
                    "completion_tokens": resp.usage.completion_tokens,
                    "total_tokens": resp.usage.total_tokens,
                }
        except Exception:  # pragma: no cover
            usage = None

        if not content and not tool_calls:
            raise LLMError("empty", MSG_UPSTREAM, "empty completion from provider")

        return LLMResultWithTools(
            content=content,
            model=model,
            tool_calls=tool_calls,
            finish_reason=getattr(choice, "finish_reason", None),
            usage=usage,
        )

    def _call(
        self,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: Optional[int] = None,
    ) -> LLMResult:
        client = self._get_client()
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=self.settings.chatbot_temperature,
                max_tokens=max_tokens or self.settings.chatbot_max_tokens,
                top_p=self.settings.chatbot_top_p,
                stream=False,
            )
        except AuthenticationError as exc:
            # Upstream rejected the API token (401). Never fall back, never leak.
            raise LLMError("auth", MSG_AUTH_FAILED, str(exc)) from exc
        except RateLimitError as exc:
            raise LLMError("rate_limit", MSG_RATE_LIMIT, str(exc)) from exc
        except APITimeoutError as exc:
            raise LLMError("timeout", MSG_TIMEOUT, str(exc)) from exc
        except NotFoundError as exc:
            raise LLMError("model_unavailable", MSG_BAD_REQUEST, str(exc)) from exc
        except BadRequestError as exc:
            raise LLMError("bad_request", MSG_BAD_REQUEST, str(exc)) from exc
        except (APIConnectionError, APIError) as exc:
            raise LLMError("upstream", MSG_UPSTREAM, str(exc)) from exc
        except LLMError:
            raise
        except Exception as exc:  # pragma: no cover - defensive catch-all
            raise LLMError("upstream", MSG_UPSTREAM, str(exc)) from exc

        answer = ""
        try:
            answer = (resp.choices[0].message.content or "").strip()
        except Exception:  # pragma: no cover - defensive
            answer = ""

        usage = None
        try:
            if getattr(resp, "usage", None) is not None:
                usage = {
                    "prompt_tokens": resp.usage.prompt_tokens,
                    "completion_tokens": resp.usage.completion_tokens,
                    "total_tokens": resp.usage.total_tokens,
                }
        except Exception:  # pragma: no cover - defensive
            usage = None

        if not answer:
            raise LLMError("empty", MSG_UPSTREAM, "empty completion from provider")

        return LLMResult(answer=answer, model=model, usage=usage)


# Module-level singleton accessor (patchable in tests).
_client_singleton: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = LLMClient()
    return _client_singleton
