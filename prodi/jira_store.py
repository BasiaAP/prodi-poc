"""Jira-backed Store — the live implementation of the four-method Store
contract (save_request / save_business_case / all_requests / all_business_cases).

Swap this in for the local JSON `Store` to make Prodi's output a real Jira
ticket instead of local storage:

    from prodi.jira_store import JiraStore
    prodi = Prodi(load_config(), store=JiraStore())

Guarded import so the package works with no `requests` install and no Jira
access (the default Store / tests / demo need neither).

Env vars: JIRA_BASE_URL (e.g. https://yourteam.atlassian.net),
JIRA_EMAIL, JIRA_API_TOKEN (https://id.atlassian.com/manage-profile/security/api-tokens).

Project/issue-type mapping comes from `config/prodi.yaml`'s `routing` +
`jira` sections — see config for the sandbox vs. production board keys.
"""
from __future__ import annotations

import os
from typing import Any, Optional

from .store import Store


class JiraStore(Store):
    def __init__(self, config: dict[str, Any], path: Optional[str] = None) -> None:
        super().__init__(path)
        self.cfg = config
        self._base = os.environ["JIRA_BASE_URL"].rstrip("/")
        self._auth = (os.environ["JIRA_EMAIL"], os.environ["JIRA_API_TOKEN"])

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        import requests  # type: ignore
        resp = requests.post(
            f"{self._base}/rest/api/3/issue", json=payload, auth=self._auth,
            headers={"Content-Type": "application/json"}, timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return {"key": data["key"], "url": f"{self._base}/browse/{data['key']}"}

    def save_request(self, record: dict[str, Any]) -> Optional[dict[str, Any]]:
        super().save_request(record)
        cls = record["classification"]
        jira_cfg = self.cfg.get("jira", {})
        is_bug = cls["kind"] in ("bug", "incident")
        project_key = (self.cfg["routing"]["incident_board"] if is_bug
                       else self.cfg["routing"]["product_board"])
        issue_type = (jira_cfg.get("incident_issue_type", "Incident") if is_bug
                      else jira_cfg.get("product_issue_type", "PREQ"))
        fields = record["fields"]
        summary = fields.get("title", "Untitled request")[:250]
        description = "\n".join(f"{k}: {v}" for k, v in fields.items())
        return self._post({
            "fields": {
                "project": {"key": project_key},
                "issuetype": {"name": issue_type},
                "summary": summary,
                "description": {
                    "type": "doc", "version": 1,
                    "content": [{"type": "paragraph", "content": [
                        {"type": "text", "text": description}]}],
                },
            }
        })

    def save_business_case(self, record: dict[str, Any]) -> None:
        super().save_business_case(record)
        # A full implementation would addCommentToJiraIssue on the request's
        # ticket with record["document"]; left for the live integration since
        # it needs the ticket key threaded through from save_request.
