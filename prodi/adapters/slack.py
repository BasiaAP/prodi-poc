"""Slack adapter — Bolt-based. Guarded import so the package works without
slack_bolt installed (the CLI adapter and tests need no Slack).

To run:  pip install "slack_bolt"  and set SLACK_BOT_TOKEN / SLACK_APP_TOKEN,
then `python -m prodi.adapters.slack`. Interactivity (the intake modal) needs
Socket Mode's `interactive` connection, which Bolt handles automatically over
the same connection as messages - no public request URL required.

Intake UX: a #req/#preq trigger opens a single Block Kit modal listing every
missing MUST HAVE (product, plus tech ones if it already looks like a bug) -
one popup, one submit, instead of asking one question per message. On
submit, the field values are rendered as "field: value" lines and fed
through the exact same core.handle() -> engine.parse_form() path a plain-text
bulk reply would use (see orchestrator._send_form_or_finish /
engine.parse_form), so the modal is a UI convenience only - the validation
logic never special-cases Slack.
"""
from __future__ import annotations

from typing import Any

from ..models import IncomingMessage, Platform, Reply
from .base import PlatformAdapter

_INTAKE_CALLBACK_ID = "prodi_intake_form"


class SlackAdapter(PlatformAdapter):
    def __init__(self, prodi, app: Any = None) -> None:
        super().__init__(prodi)
        self._app = app or self._build_app()
        self._register()

    def _build_app(self):
        import os
        from slack_bolt import App  # type: ignore
        return App(token=os.environ["SLACK_BOT_TOKEN"])

    def to_incoming(self, event: dict) -> IncomingMessage:
        return IncomingMessage(
            platform=Platform.SLACK,
            channel=event["channel"],
            user=event["user"],
            text=event.get("text", ""),
            thread_id=event.get("thread_ts") or event.get("ts"),
            raw=event,
        )

    def send(self, reply: Reply) -> None:
        self._app.client.chat_postMessage(
            channel=reply.channel,
            thread_ts=reply.thread_id,
            text=reply.text,
        )

    # -- single-form intake as a modal, instead of one question per message --
    def _missing_must_haves(self, text: str) -> list[dict[str, Any]]:
        engine = self.prodi.engine
        pool = engine.product_must_haves()
        if engine.looks_like_bug(text):
            pool = pool + engine.tech_must_haves()
        return pool

    def _build_modal(self, must_haves: list[dict[str, Any]], channel: str, thread_id: str) -> dict:
        blocks = []
        for m in must_haves:
            element: dict[str, Any] = {"type": "plain_text_input", "action_id": m["field"]}
            if m.get("options"):
                element = {
                    "type": "static_select", "action_id": m["field"],
                    "options": [{"text": {"type": "plain_text", "text": o}, "value": o}
                                for o in m["options"]],
                }
            blocks.append({
                "type": "input", "block_id": m["field"], "element": element,
                "label": {"type": "plain_text", "text": m["prompt"][:150]},
            })
        return {
            "type": "modal", "callback_id": _INTAKE_CALLBACK_ID,
            "private_metadata": f"{channel}|{thread_id}",
            "title": {"type": "plain_text", "text": "Prodi intake"},
            "submit": {"type": "plain_text", "text": "Submit"},
            "blocks": blocks,
        }

    def _register(self) -> None:
        @self._app.event("message")
        def _on_message(event, client):  # noqa: ANN001
            msg = self.to_incoming(event)
            # Drive the core first regardless - it creates/seeds the session
            # and (for a trigger) sets _awaiting_form, same as any adapter.
            replies = self.prodi.handle(msg)
            if not replies:
                return  # not a trigger, no active session for this message
            state = self.prodi._sessions.get(msg.session_key)
            just_sent_form = bool(state and state.fields.get("_awaiting_form"))
            if just_sent_form and "trigger_id" in event:
                # Swap the core's text-based form reply for a native modal -
                # same missing fields, better UI. Submission re-enters via
                # _on_submit below and is parsed by the same engine.parse_form.
                must_haves = self._missing_must_haves(msg.text)
                client.views_open(
                    trigger_id=event["trigger_id"],
                    view=self._build_modal(must_haves, msg.channel,
                                           msg.thread_id or msg.user),
                )
            else:
                for reply in replies:
                    self.send(reply)

        @self._app.view(_INTAKE_CALLBACK_ID)
        def _on_submit(ack, body, view, client):  # noqa: ANN001
            ack()
            channel, thread_id = view["private_metadata"].split("|", 1)
            values = view["state"]["values"]
            lines = []
            for block_id, actions in values.items():
                action = actions[block_id]
                value = (action.get("value")
                        or (action.get("selected_option") or {}).get("value", ""))
                lines.append(f"{block_id}: {value}")
            self.dispatch({
                "channel": channel, "user": body["user"]["id"],
                "text": "\n".join(lines), "thread_ts": thread_id,
            })

    def run(self) -> None:
        import os
        from slack_bolt.adapter.socket_mode import SocketModeHandler  # type: ignore
        SocketModeHandler(self._app, os.environ["SLACK_APP_TOKEN"]).start()


if __name__ == "__main__":
    from ..config import load_config
    from ..orchestrator import Prodi
    SlackAdapter(Prodi(load_config())).run()
