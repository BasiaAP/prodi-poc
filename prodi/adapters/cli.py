"""CLI adapter — a fully working communicator for the PoC.

Run `python -m prodi.adapters.cli` for an interactive #req session in your
terminal. It proves the whole pipeline end-to-end with no external service.
"""
from __future__ import annotations

import sys
from typing import Any

from ..models import IncomingMessage, Platform, Reply
from .base import PlatformAdapter


class CLIAdapter(PlatformAdapter):
    def __init__(self, prodi, user: str = "you", channel: str = "#req") -> None:
        super().__init__(prodi)
        self.user = user
        self.channel = channel

    def to_incoming(self, event: Any) -> IncomingMessage:
        return IncomingMessage(
            platform=Platform.CLI,
            channel=self.channel,
            user=self.user,
            text=str(event),
            thread_id=self.user,   # one session per CLI user
        )

    def send(self, reply: Reply) -> None:
        print(f"\nProdi › {reply.text}\n")

    def run(self) -> None:
        print("Prodi CLI — start a request with '#req <your request>'. "
              "Ctrl-D to quit.")
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            replies = self.dispatch(line)
            if not replies:
                print("(not a #req — ignored)")


if __name__ == "__main__":
    from ..config import load_config
    from ..orchestrator import Prodi
    CLIAdapter(Prodi(load_config())).run()
