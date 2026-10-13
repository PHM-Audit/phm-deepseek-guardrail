"""deepseek_provider.py — wire DeepSeek models into the openai-agents SDK.

The openai-agents SDK talks to any OpenAI-compatible endpoint. DeepSeek's API
is OpenAI-compatible, so the whole wiring is:

    from deepseek_provider import make_deepseek_client, DEEPSEEK_CHAT, DEEPSEEK_REASONER

    client = make_deepseek_client(api_key="sk-...")
    agent = Agent(name="x", model=DEEPSEEK_CHAT, tools=[...])

Requires: pip install openai-agents (>=0.23.1), python-dotenv optional.
API key source (first match wins): argument > DEEPSEEK_API_KEY env > ./deepseek_api_key.txt
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from openai import AsyncOpenAI

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_CHAT = "deepseek-chat"          # non-reasoning, tool-calling
DEEPSEEK_REASONER = "deepseek-reasoner"  # reasoning line (R-series)


def resolve_api_key(api_key: Optional[str] = None) -> str:
    if api_key:
        return api_key
    env = os.environ.get("DEEPSEEK_API_KEY")
    if env:
        return env.strip()
    local = Path(__file__).parent / "deepseek_api_key.txt"
    if local.exists():
        return local.read_text().strip()
    raise RuntimeError(
        "DeepSeek API key not found. Pass api_key=..., set DEEPSEEK_API_KEY, "
        "or create deepseek_api_key.txt next to this file."
    )


def make_deepseek_client(api_key: Optional[str] = None) -> AsyncOpenAI:
    """Build an AsyncOpenAI client pointed at the DeepSeek endpoint."""
    return AsyncOpenAI(base_url=DEEPSEEK_BASE_URL, api_key=resolve_api_key(api_key))


def install_as_default(api_key: Optional[str] = None, tracing: bool = False) -> AsyncOpenAI:
    """Install DeepSeek as the default OpenAI client for openai-agents."""
    from agents import set_default_openai_client, set_tracing_disabled

    client = make_deepseek_client(api_key)
    set_default_openai_client(client)
    if not tracing:
        set_tracing_disabled(True)
    return client
