"""Prodi orchestrator — the single platform-agnostic entry point.

An adapter's whole integration is: build an `IncomingMessage`, call
`prodi.handle(msg)`, render the returned `Reply` list. That's the entire
contract, so connecting Prodi to a new team's bot is one adapter + config.

Responsibilities:
  * Intake & Triage: MUST HAVES gating as a per-session state machine.
  * Route completed requests through QA -> Tech categorization ->
    Product Optimization -> (Business Case) and back with instant feedback.
"""
from __future__ import annotations

from typing import Any, Optional

from .agents import business_case, product_optimization, qa, reporting
from .engine import ValidationEngine
from .llm import LLMClient, get_llm
from .models import Decision, IncomingMessage, Reply, RequestState
from .store import Store


class Prodi:
    def __init__(self, config: dict[str, Any], store: Optional[Store] = None,
                 llm: Optional[LLMClient] = None, idea_board: Any = None,
                 squad_backlog: Any = None) -> None:
        self.cfg = config
        self.engine = ValidationEngine(config, idea_board=idea_board,
                                       squad_backlog=squad_backlog)
        self.store = store or Store()
        self.llm = llm or get_llm()
        self._sessions: dict[str, RequestState] = {}

    # -- helpers -------------------------------------------------------------
    def _reply(self, msg: IncomingMessage, text: str, **fields) -> Reply:
        return Reply(text=text, channel=msg.channel,
                     thread_id=msg.thread_id or msg.user, fields=fields)

    def _is_trigger(self, text: str) -> bool:
        t = text.strip().lower()
        return any(t.startswith(tok) for tok in self.cfg["bot"]["trigger_tokens"])

    # -- main entry point ----------------------------------------------------
    def handle(self, msg: IncomingMessage) -> list[Reply]:
        key = msg.session_key
        state = self._sessions.get(key)

        # New session only if it's a trigger; otherwise ignore stray chatter.
        if state is None:
            if not self._is_trigger(msg.text):
                return []
            state = RequestState(session_key=key, user=msg.user,
                                 channel=msg.channel, thread_id=msg.thread_id,
                                 platform=msg.platform)
            state.looks_like_bug = self.engine.looks_like_bug(msg.text)
            self._sessions[key] = state
            # Seed title/summary from the trigger line.
            seed = msg.text
            for tok in self.cfg["bot"]["trigger_tokens"]:
                if seed.lower().startswith(tok):
                    seed = seed[len(tok):].strip()
                    break
            if seed:
                state.fields["title"] = seed[:80]
                state.fields.setdefault("summary", seed)
            return self._send_form_or_finish(msg, state)

        # A pending single-field question (the one-at-a-time fallback for
        # whatever the form reply didn't cover) takes priority over a fresh
        # bulk-form parse.
        pending = state.fields.pop("_pending", None)
        if pending:
            state.fields[pending] = msg.text.strip()
            if not state.looks_like_bug:
                state.looks_like_bug = self.engine.looks_like_bug(msg.text)
            return self._advance(msg, state)

        # Bulk form reply: parse every "field: value" line in one shot.
        if state.fields.pop("_awaiting_form", None):
            parsed = self.engine.parse_form(msg.text, state)
            state.fields.update(parsed)
            if not state.looks_like_bug:
                state.looks_like_bug = self.engine.looks_like_bug(msg.text)
            return self._advance(msg, state)

        return self._advance(msg, state)

    def _send_form_or_finish(self, msg: IncomingMessage, state: RequestState) -> list[Reply]:
        """Single-form intake: ask for every missing MUST HAVE in one message
        instead of one question per message. If the trigger line already
        covered everything (unlikely but possible), skip straight to QA/routing."""
        template = self.engine.form_template(state)
        if not template:
            return self._finalize(msg, state)
        state.fields["_awaiting_form"] = "1"
        return [self._reply(
            msg,
            "Thanks — before I can process this, reply with *all* of the "
            f"following in *one message* (one field per line):\n\n{template}",
            decision=Decision.NEEDS_MORE.value)]

    # -- state machine -------------------------------------------------------
    def _advance(self, msg: IncomingMessage, state: RequestState) -> list[Reply]:
        nxt = self.engine.next_question(state)
        if nxt is not None:
            field, prompt, options = nxt
            state.fields["_pending"] = field
            hint = f"  (options: {', '.join(options)})" if options else ""
            return [self._reply(msg, f"*{prompt}*{hint}",
                                decision=Decision.NEEDS_MORE.value, field=field)]

        # Gate satisfied -> QA -> route.
        state.fields.pop("_pending", None)
        return self._finalize(msg, state)

    def _finalize(self, msg: IncomingMessage, state: RequestState) -> list[Reply]:
        qa_result = qa.check(self.engine, state)
        if not qa_result["passed"]:
            missing = ", ".join(qa_result["missing"] + qa_result["thin_fields"])
            return [self._reply(msg, f"QA: needs more detail on: {missing}",
                                decision=Decision.NEEDS_MORE.value)]

        cls = product_optimization.validate_request(self.engine, state)
        state.classification = cls
        state.stage = "triaged"

        replies: list[Reply] = []

        if cls.kind in ("bug", "incident"):
            pm = cls.owner or "unassigned — escalating"
            if cls.kind == "bug" and cls.duplicate_ref:
                # Squad backlog already covers this - reference it, no
                # second ticket. Owner still tagged so the PM sees it.
                replies.append(self._reply(
                    msg,
                    f":bug: This looks like a *bug*, not a product request — further "
                    f"assessment needed. Already tracked as *{cls.duplicate_ref}* on the "
                    f"*{cls.target_board}* squad backlog; tagging *{pm}* ({cls.owner_area}) "
                    f"instead of opening a duplicate.",
                    decision=Decision.BUG_INCIDENT.value, board=cls.target_board,
                    classification=cls.__dict__))
                self._close(state)
                return replies

            ticket = self._save_request(state, cls)
            # ticket_ref already names the board when there's no real ticket
            # (local stub); only add the squad-backlog clause when there IS
            # a real ticket, so the board isn't named twice.
            if ticket:
                ticket_ref = f"*{ticket['key']}* ({ticket['url']})"
                backlog_clause = f" on the *{cls.target_board}* squad backlog"
            else:
                ticket_ref = f"the *{cls.target_board}* board"
                backlog_clause = ""
            if cls.kind == "incident":
                text = (f":rotating_light: This looks like an *incident*, not a product "
                       f"request. Filed as {ticket_ref}. PM *{pm}* ({cls.owner_area}) "
                       f"notified and assigned.")
            else:
                text = (f":bug: This looks like a *bug*, not a product request — further "
                       f"assessment needed. No existing ticket covers it, so filed as "
                       f"{ticket_ref}{backlog_clause}; tagging *{pm}* ({cls.owner_area}) "
                       f"for triage.")
            replies.append(self._reply(msg, text, decision=Decision.BUG_INCIDENT.value,
                                       board=cls.target_board, ticket=ticket,
                                       classification=cls.__dict__))
            self._close(state)
            return replies

        # Product path: persist + reference the ticket. The reply never
        # carries the full request/business case content - that belongs on
        # the ticket, not in the channel.
        ticket = self._save_request(state, cls)
        ticket_ref = f"*{ticket['key']}* ({ticket['url']})" if ticket else f"the *{cls.target_board}* board"
        rec = (f":white_check_mark: *Accepted* — filed as {ticket_ref}.\n"
               f"• Owner: *{cls.owner or 'unassigned — escalating'}* ({cls.owner_area})\n"
               f"• Category: *{cls.category}*  |  Bucket: *{cls.bucket}*\n"
               f"• Opportunity area: *{cls.opportunity_area}*\n"
               f"• Strategy fit: *{cls.strategy}*")
        decision = Decision.ACCEPTED.value
        in_development = cls.duplicate_status == "in_development"
        if cls.duplicate_ref:
            status = "in development" if in_development else "planned"
            rec += (f"\n:link: *Already {status}*: {cls.duplicate_ref} — "
                    f"ask *{cls.owner or 'the owner'}* for details.")
            decision = Decision.DUPLICATE.value
        if cls.confidence < self.cfg["bot"]["confidence_threshold"]:
            rec += "\n:warning: Low confidence — escalating to a named owner."
        replies.append(self._reply(msg, rec, decision=decision,
                                   classification=cls.__dict__, ticket=ticket))

        # #idea logic / one-pager: triggers when there's no duplicate at all
        # ("for consideration later") or the duplicate is merely planned, no
        # date yet ("in planning") - per the PRD's Product Validations 1.b.ii
        # / 1.b.iii. It does NOT trigger when the duplicate is already in
        # development (1.b.i) - that's squad-assigned against the existing
        # item, not a fresh business case. Not gated on revenue_relevance -
        # the PRD ties this to the duplicate-check outcome, not the intake
        # field. The document is attached to the ticket, never pasted into
        # the channel.
        if not in_development:
            bc = business_case.generate(self.llm, self.cfg, self.store, state)
            case_ref = (f"*{bc['case_id']}* ({bc['url']})" if bc.get("url")
                        else f"*{bc['case_id']}* (stored locally — Confluence write not configured)")
            replies.append(self._reply(
                msg, f":page_facing_up: Business Case Overview drafted — {case_ref}.",
                decision=decision, document=bc["document"], case_id=bc["case_id"],
                ticket=ticket))
        self._close(state)
        return replies

    def _save_request(self, state: RequestState, cls) -> Optional[dict[str, Any]]:
        return self.store.save_request({
            "user": state.user,
            "platform": state.platform.value,
            "fields": {k: v for k, v in state.fields.items()
                       if not k.startswith("_")},
            "classification": cls.__dict__,
        })

    def _close(self, state: RequestState) -> None:
        state.stage = "closed"
        self._sessions.pop(state.session_key, None)

    # -- reporting passthrough ----------------------------------------------
    def weekly_report(self) -> str:
        return reporting.weekly_report(self.llm, self.cfg, self.store)
