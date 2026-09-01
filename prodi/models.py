"""Platform-agnostic data models shared by every agent and adapter.

These are the *contract* between a communicator adapter and the Prodi core.
An adapter's only job is to turn a platform event into an `IncomingMessage`
and turn the returned `Reply` objects back into platform messages.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Platform(str, Enum):
    SLACK = "slack"
    TEAMS = "teams"
    CLI = "cli"
    OTHER = "other"


class Decision(str, Enum):
    """Instant feedback categories shown to the requestor."""
    NEEDS_MORE = "needs_more"        # MUST HAVES incomplete
    ACCEPTED = "accepted"            # valid product request, routed
    BUG_INCIDENT = "bug_incident"    # filtered to the incident/bug board
    DUPLICATE = "duplicate"          # already planned / in development
    OUT_OF_SCOPE = "out_of_scope"
    POSTPONED_2027 = "postponed_2027"


@dataclass
class IncomingMessage:
    """Normalised inbound message. Adapters produce these."""
    platform: Platform
    channel: str                     # channel / conversation id
    user: str                        # requestor id or handle
    text: str
    thread_id: Optional[str] = None  # groups a multi-turn intake session
    user_email: Optional[str] = None  # requestor's email, if the adapter can
                                      # resolve one - used to set the real
                                      # Jira Reporter field (see JiraStore).
                                      # None is fine; reporter is just omitted.
    raw: Any = None                  # original platform payload (optional)

    @property
    def session_key(self) -> str:
        return f"{self.platform.value}:{self.channel}:{self.thread_id or self.user}"


@dataclass
class Reply:
    """Normalised outbound message. The core produces these; adapters render them."""
    text: str
    channel: str
    thread_id: Optional[str] = None
    # Structured payload for adapters that can render richer UI (blocks/cards).
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class Classification:
    """Output of the validation engine's categorisation step."""
    kind: str                        # "product" | "bug" | "incident"
    category: Optional[str] = None
    bucket: Optional[str] = None
    opportunity_area: Optional[str] = None
    owner: str = ""
    owner_area: str = ""
    target_board: str = ""
    strategy: Optional[str] = None
    duplicate_ref: Optional[str] = None
    duplicate_status: Optional[str] = None
    confidence: float = 1.0
    reasons: list[str] = field(default_factory=list)


@dataclass
class RequestState:
    """A request being assembled across a multi-turn intake session."""
    session_key: str
    user: str
    channel: str
    thread_id: Optional[str] = None
    platform: Platform = Platform.OTHER
    user_email: Optional[str] = None
    fields: dict[str, str] = field(default_factory=dict)
    looks_like_bug: bool = False
    stage: str = "collecting"        # collecting -> triaged -> closed
    classification: Optional[Classification] = None

    def missing(self, required: list[str]) -> list[str]:
        return [f for f in required if not self.fields.get(f)]
