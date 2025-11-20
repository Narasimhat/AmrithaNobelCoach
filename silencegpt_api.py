from typing import List, Dict, Optional

from openai import OpenAI


def _resolve_api_key(provided: Optional[str]) -> Optional[str]:
    """Resolve an API key from (in order) provided arg, secrets, env handled by OpenAI."""
    if provided:
        return provided
    try:
        import streamlit as st  # type: ignore
    except Exception:
        return None
    # Try flat key first
    if "SILENCE_GPT_API_KEY" in st.secrets:
        return st.secrets.get("SILENCE_GPT_API_KEY")
    # Then nested block: [silencegpt_api] api_key="..."
    block = st.secrets.get("silencegpt_api", {})
    if isinstance(block, dict):
        return block.get("api_key") or block.get("key")
    return None


def _build_client(api_key: Optional[str]) -> OpenAI:
    resolved = _resolve_api_key(api_key)
    if resolved:
        return OpenAI(api_key=resolved)
    # Fall back to default OpenAI resolution (env vars, config files)
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
