"""Reporting agent — drafts standardized weekly / all-hands reporting.

Owner-attributed, standard template, draft-only (human sign-off required).
Reads accumulated requests from unified storage and groups by owner.
"""
from __future__ import annotations

from typing import Any

from ..llm import LLMClient
from ..store import Store
from .base import REGISTRY


def weekly_report(llm: LLMClient, cfg: dict[str, Any], store: Store) -> str:
    by_owner: dict[str, list[str]] = {}
    for req in store.all_requests():
        cls = req.get("classification", {})
        owner = cls.get("owner") or "Unassigned"
        line = (f"- {req.get('fields', {}).get('title', 'Untitled')} "
                f"[{cls.get('target_board', '?')}] "
                f"({cls.get('category', 'n/a')})")
        by_owner.setdefault(owner, []).append(line)

    body = ["# Weekly Product Status (DRAFT — owner sign-off required)\n"]
    for owner, lines in sorted(by_owner.items()):
        body.append(f"## {owner}")
        body.extend(lines)
        body.append("")
    draft = "\n".join(body)

    agent = REGISTRY["reporting"]
    # LLM tier only polishes tone; the numbers are deterministic.
    _ = agent.think(llm, cfg, prompt="Polish this weekly status draft:\n" + draft)
    return draft
