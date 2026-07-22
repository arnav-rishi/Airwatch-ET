import asyncio
import os
import json
from openai import AsyncAzureOpenAI, AzureOpenAI

_client_kwargs = dict(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
)

client = AzureOpenAI(**_client_kwargs)
async_client = AsyncAzureOpenAI(**_client_kwargs)

DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")


def call_llm(system: str, user: str, max_tokens: int = 8000, reasoning_effort: str = "low") -> str:
    """
    Single chat completion call to Azure OpenAI. Returns the assistant message text.

    gpt-5-nano is a reasoning model: with default reasoning effort it can burn the
    entire token budget on hidden reasoning and return EMPTY output (especially for
    token-heavy scripts like Tamil/Kannada). We cap reasoning_effort at "low" so
    there is always budget left for the actual answer.
    """
    response = client.chat.completions.create(
        model=DEPLOYMENT,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_completion_tokens=max_tokens,
        reasoning_effort=reasoning_effort,
    )
    content = response.choices[0].message.content
    if not content or not content.strip():
        finish = response.choices[0].finish_reason
        usage = response.usage
        reasoning = getattr(getattr(usage, "completion_tokens_details", None), "reasoning_tokens", "?")
        raise ValueError(
            f"LLM returned empty content (finish_reason={finish!r}, "
            f"reasoning_tokens={reasoning}/{max_tokens}). The reasoning model consumed "
            "the token budget before producing output — raise max_completion_tokens "
            "or lower reasoning_effort."
        )
    return content


async def acall_llm(
    system: str, user: str, max_tokens: int = 8000, reasoning_effort: str = "low"
) -> str:
    """
    Async twin of call_llm, for use from FastAPI request handlers.

    Why this matters: the sync client blocks the event loop for the whole
    round trip. routes/intelligence.py fans out one attribution call per
    hotspot with asyncio.gather — with the sync client those coroutines run
    strictly one after another AND freeze every other request while they do,
    so the "parallel" fan-out delivered neither parallelism nor concurrency.
    """
    response = await async_client.chat.completions.create(
        model=DEPLOYMENT,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_completion_tokens=max_tokens,
        reasoning_effort=reasoning_effort,
    )
    content = response.choices[0].message.content
    if not content or not content.strip():
        finish = response.choices[0].finish_reason
        usage = response.usage
        reasoning = getattr(getattr(usage, "completion_tokens_details", None), "reasoning_tokens", "?")
        raise ValueError(
            f"LLM returned empty content (finish_reason={finish!r}, "
            f"reasoning_tokens={reasoning}/{max_tokens}). The reasoning model consumed "
            "the token budget before producing output — raise max_completion_tokens "
            "or lower reasoning_effort."
        )
    return content


def _parse_json_response(raw: str) -> dict | list:
    cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(cleaned)


_JSON_CORRECTION = (
    "\n\nCRITICAL: Your previous response was not valid JSON. "
    "Respond with ONLY the raw JSON object, nothing else."
)


def call_llm_json(system: str, user: str, max_tokens: int = 8000, _retry: bool = True) -> dict | list:
    """
    Call Azure OpenAI expecting JSON. On parse failure, retries once with an
    explicit correction instruction appended to the system prompt.
    """
    raw = call_llm(system, user, max_tokens)
    try:
        return _parse_json_response(raw)
    except json.JSONDecodeError:
        if not _retry:
            raise
        return call_llm_json(system + _JSON_CORRECTION, user, max_tokens, _retry=False)


async def acall_llm_json(
    system: str, user: str, max_tokens: int = 8000, _retry: bool = True
) -> dict | list:
    """Async twin of call_llm_json. Same one-shot correction retry."""
    raw = await acall_llm(system, user, max_tokens)
    try:
        return _parse_json_response(raw)
    except json.JSONDecodeError:
        if not _retry:
            raise
        return await acall_llm_json(system + _JSON_CORRECTION, user, max_tokens, _retry=False)
