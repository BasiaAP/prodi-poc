"""Business Case engine — standardized Business Case Overview.

Matches the existing "#idea engine" Confluence tool that already runs in the
Product Space (How to: Business Case Generator, space PT): a four-part
overview - executive one-pager, B2B2C business-model context, possible
approaches mapped to sales channels, and a SAFe lean business case - marked
"Draft for validation" and auto-numbered BC-000N. Anything not specified is
flagged as an open question rather than invented, and writes to unified
storage. Uses the Opus tier for the narrative; the channel mapping and
numbering are deterministic so the structure is always consistent.
"""
from __future__ import annotations

from typing import Any

from ..llm import LLMClient
from ..models import RequestState
from ..store import Store
from .base import REGISTRY

CHANNELS = {
    "Whitelabel": "Insurer / White-Label — monetize at the insurer buyer tier",
    "Insurance (no WL)": "Insurer — monetize at the insurer buyer tier",
    "Corporate client": "Corporate / Core — monetize at the corporate buyer tier",
    "Reseller (No WL)": "Reseller / SMB — monetize at the reseller tier",
}


def _channel_mapping(state: RequestState) -> str:
    return CHANNELS.get(state.fields.get("client_type", ""),
                        "No direct client channel — foundational / platform value")


def generate(llm: LLMClient, cfg: dict[str, Any], store: Store,
             state: RequestState) -> dict[str, Any]:
    agent = REGISTRY["business_case"]
    # Case numbering is the Store's job, not the engine's: the local JSON
    # stub counts what it has locally, while a live ConfluenceStore queries
    # the Product Space for the real current max BC-#### - so numbering
    # can't collide with cases created outside this PoC (e.g. by the real
    # daily #idea job).
    case_id = store.next_case_id()
    channel = _channel_mapping(state)
    bucket = state.classification.bucket if state.classification else "TBD"
    title = state.fields.get("title", "Untitled")

    header = f"""# {case_id} · Business Case — {title}

**Status:** DRAFT FOR VALIDATION
**Submitted by:** {state.user}
**Client:** {state.fields.get('client_name', 'n/a')} ({state.fields.get('client_type', 'n/a')})
**Summary:** {state.fields.get('summary', '')}
"""
    facts = (
        f"Sales channel: {channel}\n"
        f"Bucket: {bucket}\n"
        f"Revenue relevance: {state.fields.get('revenue_relevance', 'n/a')}\n"
        f"Budget / EBITDA impact: {state.fields.get('budget_ebitda_impact', 'n/a')}\n"
        f"Customer value: {state.fields.get('customer_value', 'n/a')}\n"
        f"Strategy fit (Q3-2026 guardrails): "
        f"{state.classification.strategy if state.classification else 'TBD'}\n"
    )
    narrative = agent.think(
        llm, cfg,
        prompt=(
            "Write the standard four-part Business Case Overview for the "
            "Product Space, in this exact order:\n"
            "1. Executive one-pager (problem / opportunity, who it's for)\n"
            "2. B2B2C business-model context\n"
            "3. Possible approaches mapped to our sales channels\n"
            "4. SAFe lean business case (cost/benefit, urgency, confidence)\n"
            "Flag anything not specified as an open question - never invent "
            f"figures.\n\nRequest facts:\n{facts}"
        ),
    )
    doc = header + "\n" + narrative + "\n"
    result = store.save_business_case({
        "case_id": case_id,
        "title": title,
        "channel": channel,
        "bucket": bucket,
        "document": doc,
    })
    return {"case_id": case_id, "title": title, "document": doc,
            "url": (result or {}).get("url")}
