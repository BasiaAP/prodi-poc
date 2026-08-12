"""Live duplicate check against a squad's real Jira backlog (bug path only).

Mirrors jira_idea_board.JiraIdeaBoardChecker's keyword-overlap approach, but
targets whichever squad board an owner rule maps to, and does NOT filter by
issue type - real backlog tickets get filed as Task/Bug/Story inconsistently
(the case that motivated this: the real duplicate found in testing, HUM-26863,
is filed as a "Task", not a "Bug" - an issue-type filter would have missed
it just as badly as no live check at all).

    from prodi.jira_squad_backlog import JiraSquadBacklogChecker
    engine = ValidationEngine(config, squad_backlog=JiraSquadBacklogChecker(config))

Guarded import, same env vars as JiraStore/JiraIdeaBoardChecker.

Owner resolution prefers the ticket's REPORTER over its assignee: in this
PRD's vocabulary "owner" means the responsible PM, and Jira's "assignee" is
typically whoever's doing the engineering work, not the PM tracking it.
Adjust if that reads backwards for how your team actually uses assignee vs.
reporter.
"""
from __future__ import annotations

import os
from typing import Any, Optional

from .jira_idea_board import _keywords, _overlap

MATCH_THRESHOLD = 0.3


class JiraSquadBacklogChecker:
    def __init__(self, config: dict[str, Any]) -> None:
        self.cfg = config
        self._base = os.environ["JIRA_BASE_URL"].rstrip("/")
        self._auth = (os.environ["JIRA_EMAIL"], os.environ["JIRA_API_TOKEN"])

    def check(self, text: str, squad_board: str) -> Optional[dict[str, Any]]:
        import requests  # type: ignore
        keywords = _keywords(text)
        if not keywords:
            return None
        clause = " OR ".join(f'text ~ "{k}"' for k in keywords)
        jql = f'project = {squad_board} AND statusCategory != Done AND ({clause})'
        resp = requests.get(
            f"{self._base}/rest/api/3/search", auth=self._auth, timeout=15,
            params={"jql": jql, "maxResults": 15,
                   "fields": "summary,assignee,reporter"},
        )
        resp.raise_for_status()
        issues = resp.json().get("issues", [])

        best, best_score = None, 0.0
        for issue in issues:
            score = _overlap(text, issue["fields"]["summary"])
            if score > best_score:
                best, best_score = issue, score
        if best is None or best_score < MATCH_THRESHOLD:
            return None

        fields = best["fields"]
        reporter = fields.get("reporter") or {}
        assignee = fields.get("assignee") or {}
        owner = reporter.get("displayName") or assignee.get("displayName", "")
        return {"ref": best["key"], "title": fields["summary"],
               "board": squad_board, "owner": owner}
