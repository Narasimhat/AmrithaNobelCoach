from typing import List, Dict, Optional

from openai import OpenAI


def _build_client(api_key: Optional[str]) -> OpenAI:
    if api_key:
        return OpenAI(api_key=api_key)
    return OpenAI()


def chat_completion(
    messages: List[Dict[str, str]],
    *,
    api_key: Optional[str] = None,
    model: str = "gpt-4.1-mini",
    temperature: float = 0.7,
    max_tokens: int = 700,
) -> str:
    """Invoke OpenAI Chat Completions for SilenceGPT."""
    client = _build_client(api_key)
    response = client.chat.completions.create(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        messages=messages,
    )
    return response.choices[0].message.content
