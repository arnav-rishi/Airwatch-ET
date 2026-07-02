import os
import json
from openai import AzureOpenAI

client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
)

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


def call_llm_json(system: str, user: str, max_tokens: int = 8000, _retry: bool = True) -> dict | list:
    """
    Call Azure OpenAI expecting JSON. On parse failure, retries once with an
    explicit correction instruction appended to the system prompt.
    """
    raw = call_llm(system, user, max_tokens)
    cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        if not _retry:
            raise
        corrected_system = system + "\n\nCRITICAL: Your previous response was not valid JSON. Respond with ONLY the raw JSON object, nothing else."
        return call_llm_json(corrected_system, user, max_tokens, _retry=False)
