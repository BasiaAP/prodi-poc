"""Info Seeker + Update agents — the release-notes pair.

Info Seeker links CORE release notes to the Product DB and seeks the
'Available by' date. Update posts the release-notes update to the public
channel once that date is set (strict gate).
"""
from __future__ import annotations

from typing import Any, Optional


def seek_available_by(release_note: dict[str, Any]) -> Optional[str]:
    """Return the 'Available by' date if present in the linked note, else None."""
    return release_note.get("available_by")


def build_update_post(release_note: dict[str, Any]) -> Optional[str]:
    """Gate: only produce a post once 'Available by' is set."""
    date = seek_available_by(release_note)
    if not date:
        return None
    return (f":rocket: *Release Notes Update* — {release_note.get('title', '')}\n"
            f"Available by *{date}*.\n{release_note.get('summary', '')}")
