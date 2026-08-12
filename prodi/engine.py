"""The consistent request-validation engine.

This is the reusable heart of Prodi. It is *platform-independent* and
*LLM-optional*: every method is deterministic and driven by config, so the
same engine backs a Slack bot, a Teams bot, or any other communicator, and
behaves identically. Agents call into it; adapters never touch it directly.

A developer wiring Prodi to a new team customises `config/prodi.yaml`
(must-haves, keywords, owners, boards) — not this file.
"""
from __future__ import annotations

import re
from typing import Any

from .models import Classification, RequestState

_FORM_LINE_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_ /]*?)\s*:\s*(.+?)\s*$")


class ValidationEngine:
    def __init__(self, config: dict[str, Any], idea_board: Any = None,
                 squad_backlog: Any = None) -> None:
        self.cfg = config
        # Optional live checker (e.g. JiraIdeaBoardChecker) against the real
        # shared idea board. None -> falls back to the seeded PoC list below.
        self.idea_board = idea_board
        # Optional live checker (e.g. JiraSquadBacklogChecker) against a
        # squad's real backlog (bug path). None -> falls back to the seeded
        # PoC list below.
        self.squad_backlog = squad_backlog

    # -- MUST HAVES gating ---------------------------------------------------
    def product_must_haves(self) -> list[dict[str, Any]]:
        return self.cfg["must_haves"]["product"]

    def tech_must_haves(self) -> list[dict[str, Any]]:
        return self.cfg["must_haves"]["tech"]

    def required_fields(self, state: RequestState) -> list[str]:
        fields = [m["field"] for m in self.product_must_haves()]
        if state.looks_like_bug:
            fields += [m["field"] for m in self.tech_must_haves()]
        return fields

    def _pool(self, state: RequestState) -> list[dict[str, Any]]:
        return self.product_must_haves() + (
            self.tech_must_haves() if state.looks_like_bug else []
        )

    def next_question(self, state: RequestState):
        """Return the (field, prompt, options) for the next missing must-have,
        or None when the gate is satisfied. Used as the one-at-a-time fallback
        for whatever a form submission didn't cover."""
        for m in self._pool(state):
            if not state.fields.get(m["field"]):
                return m["field"], m["prompt"], m.get("options")
        return None

    # -- Single-form intake ---------------------------------------------------
    # The primary intake path: one fill-in-the-blank message out, one reply
    # in, instead of asking every MUST HAVE one at a time. next_question()
    # above remains as the fallback for any field the form reply missed.
    def form_template(self, state: RequestState) -> str:
        missing = [m for m in self._pool(state) if not state.fields.get(m["field"])]
        lines = []
        for m in missing:
            hint = f" (options: {', '.join(m['options'])})" if m.get("options") else ""
            lines.append(f"{m['field']}: <{m['prompt']}{hint}>")
        return "\n".join(lines)

    def parse_form(self, text: str, state: RequestState) -> dict[str, str]:
        """Parse a bulk 'field: value' per-line reply. Unrecognised lines are
        ignored; recognised fields overwrite whatever's already collected."""
        known = {m["field"].lower(): m["field"] for m in self._pool(state)}
        found: dict[str, str] = {}
        for line in text.splitlines():
            m = _FORM_LINE_RE.match(line)
            if not m:
                continue
            key = m.group(1).strip().lower().replace(" ", "_")
            if key in known:
                found[known[key]] = m.group(2).strip()
        return found

    def is_complete(self, state: RequestState) -> bool:
        return not state.missing(self.required_fields(state))

    # -- Bug / incident vs product ------------------------------------------
    def looks_like_bug(self, text: str) -> bool:
        t = text.lower()
        cls = self.cfg["classification"]
        return any(k in t for k in cls["bug_keywords"] + cls["incident_keywords"])

    def _bug_or_incident(self, text: str) -> str:
        t = text.lower()
        cls = self.cfg["classification"]
        if any(k in t for k in cls["incident_keywords"]):
            return "incident"
        if any(k in t for k in cls["bug_keywords"]):
            return "bug"
        return "product"

    # -- Owner assignment by keyword ----------------------------------------
    def match_owner_rule(self, text: str) -> dict[str, Any]:
        t = text.lower()
        for rule in self.cfg["owners"]:
            if rule["keywords"] and any(k in t for k in rule["keywords"]):
                return rule
        return self.cfg["owners"][-1]

    def assign_owner(self, text: str) -> tuple[str, str]:
        rule = self.match_owner_rule(text)
        return rule["owner"], rule["area"]

    # -- Duplicate check against the shared idea board ----------------------
    def duplicate_check(self, text: str) -> dict[str, Any] | None:
        if self.idea_board is not None:
            return self.idea_board.check(text)
        t = text.lower()
        for idea in self.cfg.get("idea_board_seed", []):
            if any(k in t for k in idea["keywords"]):
                return idea
        return None

    # -- Duplicate check against a squad's backlog (bug path only) ----------
    def squad_duplicate_check(self, text: str, squad_board: str) -> dict[str, Any] | None:
        if self.squad_backlog is not None:
            return self.squad_backlog.check(text, squad_board)
        t = text.lower()
        for item in self.cfg.get("squad_backlog_seed", []):
            if item.get("board") == squad_board and any(k in t for k in item["keywords"]):
                return item
        return None

    # -- Category / bucket / opportunity recommendation ---------------------
    def recommend_taxonomy(self, state: RequestState) -> dict[str, str]:
        blob = " ".join(state.fields.values()).lower()

        def pick(options: list[str], hints: dict[str, list[str]], default: str) -> str:
            for label, keys in hints.items():
                if any(k in blob for k in keys):
                    return label
            return default

        category = pick(
            self.cfg["categories"],
            {
                "AI Layer": ["ai", "zoya", "companion"],
                "Reporting": ["report", "dashboard", "holistics"],
                "Custom Solutions / WLs": ["white label", "whitelabel", "wl", "insurer"],
                "User Health Data": ["health data", "biometrics", "steps"],
                "Communications / Promotions": ["notification", "promo", "campaign"],
                "New Market Expansion": ["market", "country", "expansion"],
            },
            "New Ideas (Uncategorized)",
        )
        bucket = pick(
            self.cfg["buckets"],
            {
                "Paid Upsell": ["upsell", "new sale", "premium", "paid"],
                "Foundational Build": ["platform", "foundation", "infrastructure",
                                       "architecture", "refactor"],
            },
            "Base Package",
        )
        opportunity = pick(
            self.cfg["opportunity_areas"],
            {
                "[Buyer] Prove the program is working": ["report", "dashboard", "roi"],
                "Reach more people in more markets": ["market", "expansion", "country"],
                "Build on a reliable foundation": ["platform", "foundation", "reliab"],
                "Understand my health": ["health data", "insight", "biometrics"],
            },
            "Feel the product is made for me",
        )
        return {"category": category, "bucket": bucket, "opportunity_area": opportunity}

    # -- Strategy guardrail check -------------------------------------------
    def strategy_check(self, state: RequestState) -> str:
        blob = " ".join(state.fields.values()).lower()
        if any(k in blob for k in ["integrate", "insurer", "api", "connect"]):
            return "Integrate"
        if any(k in blob for k in ["new market", "expansion", "upsell", "grow"]):
            return "Grow"
        return "Standardize"

    # -- Full validation: produce a Classification --------------------------
    def validate(self, state: RequestState) -> Classification:
        text = " ".join([state.fields.get("title", ""),
                         state.fields.get("summary", "")]) or ""
        kind = self._bug_or_incident(state.fields.get("summary", "")
                                     + " " + state.fields.get("title", ""))

        if kind in ("bug", "incident"):
            owner_text = text + " " + state.fields.get("client_name", "")
            owner_rule = self.match_owner_rule(owner_text)
            owner, area = owner_rule["owner"], owner_rule["area"]

            if kind == "incident":
                # Straight to the incident board; PM tagged, no dedup - an
                # active incident is reported as-is, never deferred.
                board = self.cfg["routing"]["incident_board"]
                return Classification(
                    kind=kind, target_board=board, owner=owner, owner_area=area,
                    confidence=0.9,
                    reasons=[f"Matched incident keywords; routed to {board}.",
                            f"Owner '{owner or 'unassigned'}' ({area})"],
                )

            # Bug: tag the owner's squad, then check that squad's backlog
            # before opening a new ticket - if something already covers this,
            # reference it instead of creating a duplicate.
            squad_board = owner_rule.get("squad_board") or self.cfg["routing"]["bug_board"]
            dup = self.squad_duplicate_check(text, squad_board)
            cls = Classification(
                kind=kind, target_board=squad_board, owner=owner, owner_area=area,
                confidence=0.9,
                reasons=[f"Matched bug keywords; squad backlog: {squad_board}.",
                        f"Owner '{owner or 'unassigned'}' ({area})"],
            )
            if dup:
                cls.duplicate_ref = dup["ref"]
                cls.target_board = dup.get("board", squad_board)
                # The existing ticket's real owner is ground truth; our
                # keyword guess is speculative and can mislabel (e.g. a bug
                # mentioning "CMS" as the tool where something was configured
                # isn't necessarily the CMS team's bug to own).
                if dup.get("owner"):
                    cls.owner = dup["owner"]
                    cls.owner_area = "existing ticket"
                cls.reasons.append(
                    f"Already tracked as {dup['ref']} on the squad backlog"
                    + (f"; owner taken from that ticket ({dup['owner']})." if dup.get("owner") else "."))
            return cls

        owner, area = self.assign_owner(text + " " + state.fields.get("client_name", ""))
        dup = self.duplicate_check(text)
        taxo = self.recommend_taxonomy(state)
        strategy = self.strategy_check(state)
        confidence = 0.9 if owner else self.cfg["bot"]["confidence_threshold"] - 0.05

        reasons = [f"Owner '{owner or 'unassigned'}' ({area})",
                   f"Category '{taxo['category']}', bucket '{taxo['bucket']}'",
                   f"Strategy fit: {strategy}"]
        cls = Classification(
            kind="product",
            category=taxo["category"],
            bucket=taxo["bucket"],
            opportunity_area=taxo["opportunity_area"],
            owner=owner,
            owner_area=area,
            strategy=strategy,
            confidence=confidence,
            reasons=reasons,
        )
        # Board routing is flat for now: real Jira board split (product vs.
        # ideas/backlog board) isn't confirmed yet, so every non-bug request
        # - duplicate or not, planned or in development - routes to the
        # product board. Duplicate status still drives the one-pager trigger
        # and the "already planned/in development" messaging; it just no
        # longer picks a different Jira project. Revisit once board naming
        # is confirmed (see the PRD's open questions).
        cls.target_board = self.cfg["routing"]["product_board"]
        if dup:
            cls.duplicate_ref = dup["ref"]
            cls.duplicate_status = dup["status"]
            cls.owner = cls.owner or dup.get("owner", "")
            cls.reasons.append(f"Duplicate of {dup['ref']} ({dup['status']}).")
        return cls
