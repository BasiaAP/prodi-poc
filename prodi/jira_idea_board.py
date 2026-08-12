"""Live duplicate check against the real shared idea board (the `PRODUCT`
Jira Product Discovery / Polaris project). Swap in for the seeded
`idea_board_seed` in config to validate new requests against the real,
current set of ideas instead of a handful of PoC placeholders:

    from prodi.jira_idea_board import JiraIdeaBoardChecker
    prodi = Prodi(load_config(), idea_board=JiraIdeaBoardChecker(config))

Guarded import so the package works with no `requests` install and no Jira
access (the default seeded check, tests, and demo need neither).

Env vars: JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN (same as JiraStore - one
Atlassian Cloud token covers Jira + Confluence).

Matching is intentionally simple for a PoC: pull the request's significant
words (>=4 chars, minus a small stopword list), JQL-search the idea board
for any of them, then score each candidate by word overlap against the
request text. The best match above MATCH_THRESHOLD counts as a duplicate.
This will misfire at the margins on both sides (near-miss false negatives,
loosely-related false positives) - it's a tunable starting point, not a
final algorithm; revisit the threshold and stopword list once tested against
more real requests.

Status mapping (Polaris workflow status -> PRD's "has a date assigned"
signal) is also a judgment call: IN_DEVELOPMENT_STATUSES lists the status
names that count as "in development"; everything else on the board counts
as "planned". Confirm/tune this list against real board conventions.
"""
from __future__ import annotations

import os
import re
from typing import Any, Optional

_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "into", "onto",
    "add", "adds", "adding", "new", "app", "user", "users", "feature",
    "improve", "improvement", "support", "enable", "allow", "make", "test",
    "they", "them", "there", "these", "those", "were", "have", "look",
    "looks", "looked", "shows", "show", "showing",
}
# Short domain terms that are meaningful despite being under the general
# 4-char minimum (which exists to filter out short noise words).
_SHORT_ALLOWLIST = {"cms", "api", "sdk", "wl", "b2b", "b2c", "sso", "ios"}
# Calibrated against real board data (see jira_squad_backlog's motivating
# case): 0.14 is the highest true-negative measured, 0.29/0.33 are measured
# true positives - 0.25 sits cleanly between them. Recalibrate as more real
# cases are tested; this is 3 data points, not a rigorous tuning pass.
MATCH_THRESHOLD = 0.25
IN_DEVELOPMENT_STATUSES = {"in delivery", "delivered", "live", "done", "shipped"}
# Keywords found is capped generously, not truncated tight - JQL handles many
# OR clauses fine, and more true signal words in the set only helps
# _overlap()'s discrimination. Order-of-appearance is still imperfect (no
# frequency/significance ranking), but a wider net catches more real matches.
_MAX_KEYWORDS = 10


def _keywords(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Z]{3,}", text.lower())
    seen: set[str] = set()
    out = []
    for w in words:
        if w in seen:
            continue
        if len(w) < 4 and w not in _SHORT_ALLOWLIST:
            continue
        if w in _STOPWORDS:
            continue
        seen.add(w)
        out.append(w)
    return out[:_MAX_KEYWORDS]


def _overlap(a: str, b: str) -> float:
    wa, wb = set(_keywords(a)), set(_keywords(b))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


class JiraIdeaBoardChecker:
    def __init__(self, config: dict[str, Any], project_key: str = "PRODUCT") -> None:
        self.cfg = config
        self.project_key = project_key
        self._base = os.environ["JIRA_BASE_URL"].rstrip("/")
        self._auth = (os.environ["JIRA_EMAIL"], os.environ["JIRA_API_TOKEN"])

    def check(self, text: str) -> Optional[dict[str, Any]]:
        import requests  # type: ignore
        keywords = _keywords(text)
        if not keywords:
            return None
        clause = " OR ".join(f'text ~ "{k}"' for k in keywords)
        jql = f"project = {self.project_key} AND issuetype = Idea AND ({clause})"
        resp = requests.get(
            f"{self._base}/rest/api/3/search", auth=self._auth, timeout=15,
            params={"jql": jql, "maxResults": 15, "fields": "summary,status,assignee"},
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

        status = best["fields"]["status"]["name"].lower()
        assignee = best["fields"].get("assignee")
        return {
            "ref": best["key"],
            "title": best["fields"]["summary"],
            "status": "in_development" if status in IN_DEVELOPMENT_STATUSES else "planned",
            "owner": assignee["displayName"] if assignee else "",
        }
