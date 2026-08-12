"""Microsoft Teams adapter — Bot Framework based. Guarded import so the
package works without botbuilder installed.

The point of this file: connecting Prodi to Teams is *only* mapping Teams'
Activity <-> IncomingMessage/Reply. Gating, validation and routing are the
exact same core used by Slack — that's the reusability guarantee.

To run: pip install botbuilder-core aiohttp, set MicrosoftAppId/Password,
then host `handle_activity` behind an aiohttp /api/messages endpoint.
"""
from __future__ import annotations

from typing import Any

from ..models import IncomingMessage, Platform, Reply
from .base import PlatformAdapter


class TeamsAdapter(PlatformAdapter):
    def __init__(self, prodi, send_fn=None) -> None:
        super().__init__(prodi)
        # send_fn(channel, thread_id, text) posts back via a TurnContext.
        self._send_fn = send_fn

    def to_incoming(self, activity: Any) -> IncomingMessage:
        # `activity` is a botbuilder Activity (or dict in tests).
        get = (activity.get if isinstance(activity, dict)
               else lambda k, d=None: getattr(activity, k, d))
        conv = get("conversation", {})
        conv_id = conv.get("id") if isinstance(conv, dict) else getattr(conv, "id", "")
        frm = get("from_property", {}) or get("from", {})
        user = (frm.get("id") if isinstance(frm, dict)
                else getattr(frm, "id", "user"))
        return IncomingMessage(
            platform=Platform.TEAMS,
            channel=conv_id,
            user=user,
            text=get("text", "") or "",
            thread_id=conv_id,
            raw=activity,
        )

    def send(self, reply: Reply) -> None:
        if self._send_fn is None:
            raise RuntimeError("TeamsAdapter needs a send_fn bound to a TurnContext")
        self._send_fn(reply.channel, reply.thread_id, reply.text)

    async def handle_activity(self, turn_context) -> None:  # noqa: ANN001
        """Wire this into your ActivityHandler.on_message_activity."""
        self._send_fn = lambda ch, th, text: turn_context.send_activity(text)
        self.dispatch(turn_context.activity)

    def run(self) -> None:  # pragma: no cover - hosting is app-specific
        raise NotImplementedError(
            "Host handle_activity behind an aiohttp /api/messages endpoint.")
