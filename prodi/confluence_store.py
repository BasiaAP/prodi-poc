"""Confluence-backed Store — the live implementation of
Store.save_business_case(), matching the existing "#idea engine" tool
(How to: Business Case Generator, Product Space PT): publishes the drafted
Business Case Overview as a real page instead of local JSON storage.

    from prodi.confluence_store import ConfluenceStore
    prodi = Prodi(load_config(), store=ConfluenceStore(config))

Guarded import so the package works with no `requests` install and no
Confluence access (the default Store / tests / demo need neither).

Env vars: CONFLUENCE_BASE_URL (e.g. https://yourteam.atlassian.net/wiki),
CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN
(https://id.atlassian.com/manage-profile/security/api-tokens - the same
token works for both Jira and Confluence on one Atlassian Cloud site).

Case numbering queries the Product Space for the real current max BC-####
before assigning the next one (see next_case_id below) - it does not trust a
local counter, since that collides with cases created outside this process
(e.g. the real daily #idea job also writing into the same space).
"""
from __future__ import annotations

import os
import re
from typing import Any, Optional

from .store import Store

_CASE_NUM_RE = re.compile(r"BC-(\d+)")


class ConfluenceStore(Store):
    def __init__(self, config: dict[str, Any], path: Optional[str] = None) -> None:
        super().__init__(path)
        self.cfg = config
        self._base = os.environ["CONFLUENCE_BASE_URL"].rstrip("/")
        self._auth = (os.environ["CONFLUENCE_EMAIL"], os.environ["CONFLUENCE_API_TOKEN"])

    def next_case_id(self) -> str:
        import requests  # type: ignore
        space_key = self.cfg.get("business_case", {}).get("space_key", "PT")
        resp = requests.get(
            f"{self._base}/rest/api/content/search", auth=self._auth, timeout=15,
            params={"cql": f'space="{space_key}" AND title~"BC-" AND type=page',
                   "limit": 100},
        )
        resp.raise_for_status()
        nums = [int(m.group(1)) for r in resp.json().get("results", [])
                for m in [_CASE_NUM_RE.search(r.get("title", ""))] if m]
        return f"BC-{(max(nums) + 1) if nums else 1:04d}"

    def save_business_case(self, record: dict[str, Any]) -> Optional[dict[str, Any]]:
        super().save_business_case(record)
        import requests  # type: ignore
        space_key = self.cfg.get("business_case", {}).get("space_key", "PT")
        resp = requests.post(
            f"{self._base}/api/v2/pages", auth=self._auth, timeout=15,
            headers={"Content-Type": "application/json"},
            json={
                "spaceId": space_key,
                "status": "current",
                "title": f"{record['case_id']}_{record['title']}",
                "body": {"representation": "storage",
                        "value": _markdown_to_storage(record["document"])},
            },
        )
        resp.raise_for_status()
        page_id = resp.json()["id"]
        return {"url": f"{self._base}/spaces/{space_key}/pages/{page_id}"}


def _markdown_to_storage(doc: str) -> str:
    """Minimal markdown -> Confluence storage-format conversion (headings +
    paragraphs) - enough for the PoC's generated template. A production
    integration should use a real converter or write ADF/HTML directly."""
    parts = []
    for line in doc.splitlines():
        if line.startswith("# "):
            parts.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("## "):
            parts.append(f"<h2>{line[3:]}</h2>")
        elif line.strip():
            parts.append(f"<p>{line}</p>")
    return "\n".join(parts)
