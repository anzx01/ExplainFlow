import asyncio
import json
import logging
import time
from typing import TypeVar

from openai import AsyncOpenAI
from openai import RateLimitError, APIError, Timeout as OpenAITimeout

from .config import settings
from .validation import safe_parse_json, ValidationError as SchemaValidationError

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None
_client_key: tuple[str, str] | None = None
_last_preflight_ok_at = 0.0

T = TypeVar("T")


class LLMUnavailableError(RuntimeError):
    """Raised when the configured large model cannot be reached."""


class LLMResponseParseError(RuntimeError):
    """Raised when the LLM response cannot be parsed."""


def _exception_summary(exc: Exception) -> str:
    """Return useful provider diagnostics without exposing credentials."""
    status_code = getattr(exc, "status_code", None)
    request_id = getattr(exc, "request_id", None)
    message = str(exc).strip() or exc.__class__.__name__
    if settings.openai_api_key:
        message = message.replace(settings.openai_api_key, "[redacted]")
    if len(message) > 360:
        message = message[:360] + "..."
    parts = [exc.__class__.__name__]
    if status_code is not None:
        parts.append(f"status={status_code}")
    if request_id:
        parts.append(f"request_id={request_id}")
    parts.append(message)
    return " ".join(parts)


def _effective_llm_config() -> tuple[str, str]:
    """Runtime settings override .env without a service restart."""
    from src.core import runtime_settings

    base = runtime_settings.get_override("llm_base_url") or settings.openai_base_url
    key = runtime_settings.get_override("llm_api_key") or settings.openai_api_key
    return base, key


def _effective_model(model: str | None) -> str:
    from src.core import runtime_settings

    if model:
        return model
    override = runtime_settings.get_override("llm_model")
    return override or settings.llm_model


def get_client() -> AsyncOpenAI:
    global _client, _client_key
    base_url, api_key = _effective_llm_config()
    cache_key = (base_url, api_key)
    if _client is None or _client_key != cache_key:
        _client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )
    return _client


def _format_llm_unavailable(exc: Exception | str) -> str:
    detail = _exception_summary(exc) if isinstance(exc, Exception) else str(exc).strip()
    if len(detail) > 240:
        detail = detail[:240] + "..."
    base = (
        "大模型暂时连接不上，已停止本次任务；请检查 OPENAI_API_KEY、"
        "OPENAI_BASE_URL、模型名和网络后重试。"
    )
    return f"{base} 详情：{detail}" if detail else base


def _is_retriable_error(exc: Exception) -> bool:
    """Determine if an error is transient and worth retrying."""
    if isinstance(exc, RateLimitError):
        return True
    if isinstance(exc, APIError):
        return exc.status_code in {408, 429, 500, 502, 503, 504}
    if isinstance(exc, OpenAITimeout):
        return True
    if isinstance(exc, asyncio.TimeoutError):
        return True
    if isinstance(exc, OSError):
        return True
    return False


async def _call_with_retry(
    call_fn,
    max_retries: int | None = None,
    base_delay: float | None = None,
) -> any:
    """Execute a callable with exponential backoff retry for transient errors.

    Args:
        call_fn: An async callable that performs the LLM call.
        max_retries: Maximum number of retry attempts. Defaults to settings.llm_max_retries.
        base_delay: Base delay in seconds for exponential backoff. Defaults to settings.llm_retry_base_delay_s.

    Returns:
        The result of call_fn.

    Raises:
        LLMUnavailableError: If all retries are exhausted.
    """
    if max_retries is None:
        max_retries = settings.llm_max_retries
    if base_delay is None:
        base_delay = settings.llm_retry_base_delay_s

    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return await call_fn()
        except Exception as exc:
            last_exc = exc
            if attempt >= max_retries:
                break
            if not _is_retriable_error(exc):
                logger.warning(
                    "[LLM] Non-retriable error on attempt %d/%d: %s",
                    attempt + 1,
                    max_retries + 1,
                    exc,
                )
                break

            delay = base_delay * (2 ** attempt)
            delay = min(delay, 30.0)
            logger.warning(
                "[LLM] Retriable error on attempt %d/%d, retrying in %.1fs: %s",
                attempt + 1,
                max_retries + 1,
                delay,
                exc,
            )
            await asyncio.sleep(delay)

    detail = _format_llm_unavailable(last_exc or "Unknown error")
    logger.error(
        "[LLM] request failed after %d attempt(s): model=%s base_url=%s error=%s",
        (max_retries or 0) + 1,
        settings.llm_model,
        settings.openai_base_url,
        _exception_summary(last_exc) if last_exc else "Unknown error",
    )
    raise LLMUnavailableError(detail)


async def check_llm_connection(model: str | None = None, force: bool = False) -> dict:
    """Fast preflight check used before starting side-effectful work."""
    global _last_preflight_ok_at

    now = time.monotonic()
    if (
        not force
        and _last_preflight_ok_at
        and now - _last_preflight_ok_at < settings.llm_preflight_ttl_s
    ):
        return {
            "status": "ok",
            "cached": True,
            "model": _effective_model(model),
            "base_url": settings.openai_base_url,
        }

    if not settings.openai_api_key:
        raise LLMUnavailableError(_format_llm_unavailable("OPENAI_API_KEY is empty"))

    async def _ping() -> None:
        client = get_client()
        resp = await client.chat.completions.create(
            model=_effective_model(model),
            messages=[
                {
                    "role": "system",
                    "content": "You are a connectivity health check. Return JSON only.",
                },
                {"role": "user", "content": '{"ok": true}'},
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=8,
        )
        content = resp.choices[0].message.content or "{}"
        data = json.loads(content)
        if data.get("ok") is not True:
            raise RuntimeError(f"Unexpected health-check response: {content}")

    try:
        # A transient provider timeout should not abort a graph request before
        # the real call has had a chance to retry.
        await asyncio.wait_for(
            _call_with_retry(_ping, max_retries=1, base_delay=0.5),
            timeout=max(settings.llm_preflight_timeout_s, 15.0),
        )
    except Exception as exc:
        logger.error(
            "[LLM] preflight failed: model=%s base_url=%s error=%s",
            _effective_model(model),
            settings.openai_base_url,
            _exception_summary(exc),
        )
        if isinstance(exc, LLMUnavailableError):
            raise
        raise LLMUnavailableError(_format_llm_unavailable(exc)) from exc

    _last_preflight_ok_at = time.monotonic()
    return {
        "status": "ok",
        "cached": False,
        "model": _effective_model(model),
        "base_url": settings.openai_base_url,
    }


async def chat_json(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.3,
    max_retries: int | None = None,
) -> dict:
    """Call LLM and parse JSON response with automatic retry.

    Args:
        messages: List of message dicts for the chat completion.
        model: Optional model override.
        temperature: Sampling temperature (default 0.3).
        max_retries: Override for max retry attempts.

    Returns:
        Parsed JSON response from the LLM.

    Raises:
        LLMUnavailableError: If all retries are exhausted.
        LLMResponseParseError: If the response cannot be parsed as JSON.
    """
    async def _call(active_messages: list[dict]):
        client = get_client()
        return await client.chat.completions.create(
            model=_effective_model(model),
            messages=active_messages,
            response_format={"type": "json_object"},
            temperature=temperature,
            max_tokens=settings.llm_json_max_tokens,
        )

    active_messages = list(messages)
    last_error: Exception | None = None
    parse_attempts = max(0, settings.llm_json_parse_retries) + 1
    for parse_attempt in range(parse_attempts):
        response = await _call_with_retry(lambda: _call(active_messages), max_retries=max_retries)
        choice = response.choices[0]
        content = choice.message.content or "{}"
        finish_reason = getattr(choice, "finish_reason", None)
        try:
            if finish_reason == "length":
                raise SchemaValidationError("LLM JSON response was truncated by the output token limit")
            return safe_parse_json(content)
        except (SchemaValidationError, json.JSONDecodeError) as exc:
            last_error = exc
            if parse_attempt + 1 >= parse_attempts:
                break
            logger.warning(
                "[LLM] Invalid/truncated JSON on parse attempt %d/%d; requesting compact JSON: %s",
                parse_attempt + 1,
                parse_attempts,
                exc,
            )
            active_messages = list(messages) + [{
                "role": "system",
                "content": (
                    "Your previous JSON response was truncated or invalid. Return the complete JSON object again in a compact form. "
                    "Do not use markdown. Keep only required fields. Shorten narration, descriptions, labels, and arrays; never cut off a string or omit closing braces."
                ),
            }]
    raise LLMResponseParseError(str(last_error or "Unable to parse LLM JSON response")) from last_error


async def chat_text(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.5,
    max_retries: int | None = None,
) -> str:
    """Call LLM and return plain text with automatic retry.

    Args:
        messages: List of message dicts for the chat completion.
        model: Optional model override.
        temperature: Sampling temperature (default 0.5).
        max_retries: Override for max retry attempts.

    Returns:
        Text response from the LLM.

    Raises:
        LLMUnavailableError: If all retries are exhausted.
    """
    async def _call() -> str:
        client = get_client()
        resp = await client.chat.completions.create(
            model=_effective_model(model),
            messages=messages,
            temperature=temperature,
        )
        return resp.choices[0].message.content or ""

    return await _call_with_retry(_call, max_retries=max_retries)
