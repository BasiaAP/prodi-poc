"""Product Optimization agent — validate, dedup, strategy-check, assign owner.

Deterministic: delegates to the ValidationEngine so results are identical
across every communicator. The LLM tier is reserved for free-text roadmap
Q&A (see `answer_roadmap_question`), not for the routing decision.
"""
from __future__ import annotations

from typing import Any

from ..engine import ValidationEngine
from ..llm import LLMClient
from ..models import Classification, RequestState
from .base import REGISTRY


def validate_request(engine: ValidationEngine, state: RequestState) -> Classification:
    return engine.validate(state)


def answer_roadmap_question(llm: LLMClient, cfg: dict[str, Any],
                            question: str, context: str) -> str:
    agent = REGISTRY["product_optimization"]
    prompt = (f"Roadmap question: {question}\n\nRoadmap/context:\n{context}\n\n"
              "Answer with the status and the reference epic/owner, or name the "
              "owner to ask. Cite the source.")
    return agent.think(llm, cfg, prompt)
