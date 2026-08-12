"""PlatformAdapter — the one interface a developer implements to connect
Prodi to any communicator.

Contract (three methods):
  * to_incoming(event)  -> IncomingMessage   (normalise inbound)
  * send(reply)         -> None              (render + deliver outbound)
  * run()               -> None              (start the platform event loop)

Everything else — gating, validation, routing, downstream agents — is shared
and lives in the Prodi core. That's what makes the validation engine
'consistent' across Slack, Teams, or anything else.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..models import IncomingMessage, Reply
from ..orchestrator import Prodi


class PlatformAdapter(ABC):
    def __init__(self, prodi: Prodi) -> None:
        self.prodi = prodi

    @abstractmethod
    def to_incoming(self, event: Any) -> IncomingMessage:
        """Turn a raw platform event into a normalised IncomingMessage."""

    @abstractmethod
    def send(self, reply: Reply) -> None:
        """Render a Reply back to the platform."""

    @abstractmethod
    def run(self) -> None:
        """Start listening for platform events."""

    def dispatch(self, event: Any) -> list[Reply]:
        """Shared glue: normalise -> core -> deliver. Adapters call this from
        their event handler and never re-implement the pipeline."""
        msg = self.to_incoming(event)
        replies = self.prodi.handle(msg)
        for reply in replies:
            self.send(reply)
        return replies
