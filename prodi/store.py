"""Unified storage — the 'single source of truth' from the requirements.

In-memory + JSON-file backed so the PoC persists across runs without a DB.
Swap this class for a Jira/Confluence-backed implementation in production; the
rest of the system only depends on the four methods below.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional


class Store:
    def __init__(self, path: Optional[str] = None) -> None:
        self._path = path
        self._data: dict[str, list[dict[str, Any]]] = {
            "requests": [],
            "business_cases": [],
            "reports": [],
        }
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                self._data = json.load(fh)

    def _flush(self) -> None:
        if self._path:
            with open(self._path, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2)

    def save_request(self, record: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Persist a triaged request. Returns None for this local JSON stub;
        a Jira-backed Store returns {"key": "PREQS-123", "url": "..."} so the
        orchestrator can reference the real ticket instead of inventing one."""
        self._data["requests"].append(record)
        self._flush()
        return None

    def save_business_case(self, record: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Persist a drafted business case. Returns None for this local JSON
        stub; a Confluence-backed Store returns {"url": "..."} for the real
        published page in the Product Space."""
        self._data["business_cases"].append(record)
        self._flush()
        return None

    def all_requests(self) -> list[dict[str, Any]]:
        return list(self._data["requests"])

    def all_business_cases(self) -> list[dict[str, Any]]:
        return list(self._data["business_cases"])

    def next_case_id(self) -> str:
        """Next BC-#### case id. This local stub just counts what it has
        seen; a Confluence-backed Store must instead query the Product Space
        for the real current max, so numbering can't collide with cases
        created outside this process (e.g. the real daily #idea job)."""
        return f"BC-{len(self._data['business_cases']) + 1:04d}"
