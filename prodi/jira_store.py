"""Jira-backed Store — the live implementation of the four-method Store
contract (save_request / save_business_case / all_requests / all_business_cases).

Swap this in for the local JSON `Store` to make Prodi's output a real Jira
ticket instead of local storage:

    from prodi.jira_store import JiraStore
    prodi = Prodi(load_config(), store=JiraStore(config))

Guarded import so the package works with no `requests` install and no Jira
access (the default Store / tests / demo need neither).

Env vars: JIRA_BASE_URL (e.g. https://yourteam.atlassian.net),
JIRA_EMAIL, JIRA_API_TOKEN (https://id.atlassian.com/manage-profile/security/api-tokens).

The target project is `classification.target_board`, which the engine has
already resolved (incident board / a squad's backlog for bugs / the product
board) - this does NOT recompute it from routing config, since that
duplicated (and could disagree with) the engine's own decision, including
the squad_board-per-owner and duplicate-ticket overrides.

For PREQ (product) tickets, the real create-screen's custom fields are set
directly (Application(s), Affected services, Client Type, Client Name,
Revenue Relevance, Revenue Impact) - field/customfield IDs and allowed
option values were fetched live via getJiraIssueTypeMetaWithFields against
PREQS's PREQ issue type. Bug/incident tickets don't set these; they go to a
different project/issue type with a different (unconfirmed) schema, so only
summary/description are set for those.
"""
from __future__ import annotations

import os
from typing import Any, Optional

from .store import Store

# customfield IDs for PREQS/PREQ, fetched live from the real schema. If the
# real form's fields are ever changed in Jira, these need re-fetching -
# there's no way to discover them except via getJiraIssueTypeMetaWithFields.
_PREQ_FIELD_IDS = {
    "applications": "customfield_10756",     # multicheckboxes
    "affected_services": "customfield_10755",  # multicheckboxes
    "client_type": "customfield_11286",      # select
    "client_name": "customfield_11287",      # text
    "revenue_relevance": "customfield_11288",  # select
    "revenue_impact": "customfield_11289",   # text
}
_PREQ_MULTI_FIELDS = {"applications", "affected_services"}
_PREQ_SELECT_FIELDS = {"client_type", "revenue_relevance"}


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

    def _resolve_reporter_account_id(self, email: Optional[str]) -> Optional[str]:
        """Look up a Jira account by email for the Reporter field. Returns
        None (reporter omitted, Jira defaults to the API-authenticated user)
        on any miss - a failed lookup should never block ticket creation."""
        if not email:
            return None
        import requests  # type: ignore
        try:
            resp = requests.get(
                f"{self._base}/rest/api/3/user/search", auth=self._auth,
                params={"query": email}, timeout=10,
            )
            resp.raise_for_status()
            users = resp.json()
            return users[0]["accountId"] if users else None
        except Exception:
            return None

    def save_request(self, record: dict[str, Any]) -> Optional[dict[str, Any]]:
        super().save_request(record)
        cls = record["classification"]
        jira_cfg = self.cfg.get("jira", {})
        project_key = cls["target_board"]
        if cls["kind"] == "incident":
            issue_type = jira_cfg.get("incident_issue_type", "Incident")
        elif cls["kind"] == "bug":
            issue_type = jira_cfg.get("bug_issue_type", "Bug")
        else:
            issue_type = jira_cfg.get("product_issue_type", "PREQ")

        state_fields = record["fields"]
        summary = state_fields.get("title", "Untitled request")[:250]
        issue_fields: dict[str, Any] = {
            "project": {"key": project_key},
            "issuetype": {"name": issue_type},
            "summary": summary,
        }

        if cls["kind"] == "product":
            description = state_fields.get("description", "")
            for our_key, field_id in _PREQ_FIELD_IDS.items():
                value = state_fields.get(our_key)
                if not value:
                    continue
                if our_key in _PREQ_MULTI_FIELDS:
                    issue_fields[field_id] = [{"value": v.strip()}
                                              for v in value.split(",") if v.strip()]
                elif our_key in _PREQ_SELECT_FIELDS:
                    issue_fields[field_id] = {"value": value}
                else:
                    issue_fields[field_id] = value
        else:
            # Bug/incident projects have their own (unconfirmed) schema -
            # fold every collected field into the description as text rather
            # than guessing at custom field IDs that don't apply here.
            description = "\n".join(f"{k}: {v}" for k, v in state_fields.items())

        issue_fields["description"] = {
            "type": "doc", "version": 1,
            "content": [{"type": "paragraph", "content": [
                {"type": "text", "text": description}]}],
        }

        account_id = self._resolve_reporter_account_id(record.get("user_email"))
        if account_id:
            issue_fields["reporter"] = {"id": account_id}

        return self._post({"fields": issue_fields})

    def save_business_case(self, record: dict[str, Any]) -> None:
        super().save_business_case(record)
        # A full implementation would addCommentToJiraIssue on the request's
        # ticket with record["document"]; left for the live integration since
        # it needs the ticket key threaded through from save_request.
