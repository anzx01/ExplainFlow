import asyncio
import json
import time

from openai import AsyncOpenAI

from .config import settings

_client: AsyncOpenAI | None = None
_last_preflight_ok_at = 0.0


class LLMUnavailableError(RuntimeError):
    """Raised when the configured large model cannot be reached."""


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )
    return _client


def _format_llm_unavailable(exc: Exception | str) -> str:
    detail = str(exc).strip() if isinstance(exc, Exception) else str(exc).strip()
    if len(detail) > 240:
        detail = detail[:240] + "..."
    base = (
        "大模型暂时连接不上，已停止本次任务；请检查 OPENAI_API_KEY、"
        "OPENAI_BASE_URL、模型名和网络后重试。"
    )
    return f"{base} 详情：{detail}" if detail else base


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
            "model": model or settings.llm_model,
            "base_url": settings.openai_base_url,
        }

    if not settings.openai_api_key:
        raise LLMUnavailableError(_format_llm_unavailable("OPENAI_API_KEY is empty"))

    async def _ping() -> None:
        client = get_client()
        resp = await client.chat.completions.create(
            model=model or settings.llm_model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a connectivity health check. Return JSON only.",
                },
                {"role": "user", "content": '{"ok": true}'},
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=20,
        )
        content = resp.choices[0].message.content or "{}"
        data = json.loads(content)
        if data.get("ok") is not True:
            raise RuntimeError(f"Unexpected health-check response: {content}")

    try:
        await asyncio.wait_for(_ping(), timeout=settings.llm_preflight_timeout_s)
    except Exception as exc:
        raise LLMUnavailableError(_format_llm_unavailable(exc)) from exc

    _last_preflight_ok_at = time.monotonic()
    return {
        "status": "ok",
        "cached": False,
        "model": model or settings.llm_model,
        "base_url": settings.openai_base_url,
    }


async def chat_json(messages: list[dict], model: str | None = None) -> dict:
    """Call LLM and parse JSON response."""
    import json

    client = get_client()
    resp = await client.chat.completions.create(
        model=model or settings.llm_model,
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0.3,
    )
    content = resp.choices[0].message.content or "{}"
    return json.loads(content)


async def chat_text(messages: list[dict], model: str | None = None) -> str:
    """Call LLM and return plain text."""
    client = get_client()
    resp = await client.chat.completions.create(
        model=model or settings.llm_model,
        messages=messages,
        temperature=0.5,
    )
    return resp.choices[0].message.content or ""
