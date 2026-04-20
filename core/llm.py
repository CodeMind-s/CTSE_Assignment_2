"""Ollama client factory."""
import os
from langchain_ollama import ChatOllama


DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
DEFAULT_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


def get_llm(model: str | None = None, temperature: float = 0.1) -> ChatOllama:
    """Return a configured Ollama chat client.

    Args:
        model: Override model name. Defaults to env OLLAMA_MODEL or qwen2.5:3b.
        temperature: Sampling temperature; 0.1 keeps JSON outputs stable.

    Returns:
        A ChatOllama instance ready for `.invoke([{'role': ..., 'content': ...}])`.
    """
    return ChatOllama(
        model=model or DEFAULT_MODEL,
        base_url=DEFAULT_BASE_URL,
        temperature=temperature,
    )
