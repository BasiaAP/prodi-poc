"""QA agent (Oscar-based) — deterministic completeness & quality check.

Runs before routing: confirms MUST HAVES are present and surfaces missing
content via keyword scanning. Returns a checklist result the orchestrator
attaches to the request record.
"""
from __future__ import annotations

from ..engine import ValidationEngine
from ..models import RequestState


def check(engine: ValidationEngine, state: RequestState) -> dict:
    required = engine.required_fields(state)
    missing = state.missing(required)
    # Oscar-style shallow keyword scan for thin / placeholder content.
    thin = [f for f, v in state.fields.items()
            if v and len(v.strip()) < 3]
    return {
        "complete": not missing,
        "missing": missing,
        "thin_fields": thin,
        "passed": not missing and not thin,
    }
