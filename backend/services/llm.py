import os
import json
from openai import AzureOpenAI

client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
)

DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")


def call_llm(system: str, user: str, max_tokens: int = 6000) -> str:
    """Single chat completion call to Azure OpenAI. Returns the assistant message text."""
    response = client.chat.completions.create(
        model=DEPLOYMENT,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_completion_tokens=max_tokens,
    )
    content = response.choices[0].message.content
    if content is None:
        finish = response.choices[0].finish_reason
        raise ValueError(
            f"LLM returned empty content (finish_reason={finish!r}). "
            "The reasoning model consumed all tokens before producing output — "
            "increase max_completion_tokens."
        )
    return content


def call_llm_json(system: str, user: str, max_tokens: int = 6000, _retry: bool = True) -> dict | list:
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
