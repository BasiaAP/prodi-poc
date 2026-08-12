"""Agent base class + declarative registry.

Every Prodi agent declares its logical model tier, temperature, and rules
(personality/guardrails), exactly as specified in the PoC agent table. The
concrete model id is resolved from config at call time, so the Opus/Sonnet/
Haiku split lives in one place and can be re-tuned without touching agents.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..engine import ValidationEngine
from ..llm import LLMClient


@dataclass
class Agent:
    key: str
    name: str
    tier: str                        # "opus" | "sonnet" | "haiku"
    temperature: float
    rules: str                       # personality & guardrails (system prompt)
    purpose: str = ""

    def model_id(self, cfg: dict[str, Any]) -> str:
        return cfg["models"][self.tier]

    def think(self, llm: LLMClient, cfg: dict[str, Any], prompt: str) -> str:
        """Run the agent's LLM tier. Used for generative steps (business case,
        reporting). Deterministic agents use the engine instead and never call
        this."""
        return llm.complete(
            model=self.model_id(cfg),
            temperature=self.temperature,
            system=self.rules,
            prompt=prompt,
        )


# --- The reusable agent set, straight from the PoC agent table ---------------
REGISTRY: dict[str, Agent] = {
    "intake_triage": Agent(
        key="intake_triage",
        name="Intake & Triage",
        tier="sonnet",
        temperature=0.15,
        purpose="Single entry point; enforces MUST HAVES gating and routes.",
        rules=("You are a strict gatekeeper. Do not process a request until all "
               "MUST HAVES are collected. Ask one question at a time. Never guess "
               "the classification."),
    ),
    "product_optimization": Agent(
        key="product_optimization",
        name="Product Optimization",
        tier="opus",
        temperature=0.3,
        purpose="Validate vs roadmap, dedup, strategy check, assign owner/board.",
        rules=("Always cite the source (epic/ticket/owner). Never fabricate "
               "roadmap status. Escalate to the named owner when unclear."),
    ),
    "business_case": Agent(
        key="business_case",
        name="Business Case engine",
        tier="opus",
        temperature=0.5,
        purpose="Generate a standardized Business Case Overview (B2B2C + channels).",
        rules=("Follow the business-case template. Always map to the customer "
               "models and Q3-2026 guardrails. Flag data gaps instead of "
               "inventing figures."),
    ),
    "qa": Agent(
        key="qa",
        name="QA agent (Oscar-based)",
        tier="sonnet",
        temperature=0.1,
        purpose="Completeness & quality check; filter incidents/bugs; parity.",
        rules=("Deterministic checklist. Flag missing MUST HAVES. Send incidents "
               "to the incident board."),
    ),
    "tech_categorization": Agent(
        key="tech_categorization",
        name="Tech / Categorization",
        tier="haiku",
        temperature=0.1,
        purpose="Classify incident/bug vs product; feasibility categorization only.",
        rules=("Categorization only. Engineering build work stays out of scope. "
               "Tag with category & target board."),
    ),
    "reporting": Agent(
        key="reporting",
        name="Reporting agent",
        tier="sonnet",
        temperature=0.2,
        purpose="Draft standardized weekly / all-hands reporting from the roadmap.",
        rules=("Standard template. Owner-attributed. Produce a draft only: human "
               "sign-off required."),
    ),
    "info_seeker": Agent(
        key="info_seeker",
        name="Info Seeker",
        tier="sonnet",
        temperature=0.1,
        purpose="Link CORE release notes to the Product DB; seek 'Available by' date.",
        rules=("Works on the release cadence (2-week cycle). Human sign-off "
               "required."),
    ),
    "update": Agent(
        key="update",
        name="Update agent",
        tier="haiku",
        temperature=0.1,
        purpose="Post Release Notes update to the public channel once date is set.",
        rules=("Strict gatekeeper: do not post until the 'Available by' field is "
               "set."),
    ),
}
