"""LLM abstraction with a deterministic stub backend.

Why a stub? The PoC must run in any sandbox with no API keys and still show
the full flow. `StubLLM` returns short, deterministic text so tests and the
CLI demo are reproducible. Set PRODI_LLM=anthropic (and ANTHROPIC_API_KEY) to
route the same calls to real models per the tier chosen by each agent.
"""
from __future__ import annotations

import os
from typing import Protocol


class LLMClient(Protocol):
    def complete(self, *, model: str, temperature: float,
                 system: str, prompt: str) -> str: ...


class StubLLM:
    """Deterministic, offline backend. Echoes intent so flows are visible."""

    def complete(self, *, model: str, temperature: float,
                 system: str, prompt: str) -> str:
        head = prompt.strip().splitlines()[0] if prompt.strip() else ""
        return f"[stub:{model}] {head[:180]}"


class AnthropicLLM:
    """Thin wrapper over the Anthropic SDK; imported lazily so the stub path
    has zero dependencies."""

    def __init__(self) -> None:
        from anthropic import Anthropic  # noqa: WPS433 (optional dependency)
        self._client = Anthropic()

    def complete(self, *, model: str, temperature: float,
                 system: str, prompt: str) -> str:
        msg = self._client.messages.create(
            model=model,
            max_tokens=1024,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(
            block.text for block in msg.content if getattr(block, "type", "") == "text"
        )


def get_llm() -> LLMClient:
    if os.getenv("PRODI_LLM", "stub").lower() == "anthropic":
        return AnthropicLLM()
    return StubLLM()
