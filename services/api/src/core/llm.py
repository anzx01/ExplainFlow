from openai import AsyncOpenAI

from .config import settings

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )
    return _client


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
