"""Prodi — a reusable, multi-agent Product BOT core.

Public API:
    from prodi import Prodi, load_config
    prodi = Prodi(load_config())
    replies = prodi.handle(incoming_message)
"""
from .config import load_config
from .models import IncomingMessage, Platform, Reply, Decision
from .orchestrator import Prodi

__all__ = ["Prodi", "load_config", "IncomingMessage", "Reply", "Platform", "Decision"]
