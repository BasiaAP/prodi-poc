"""Config loader (YAML). This is the single file other teams edit to re-skin
Prodi for their communicator: must-haves, keywords, owners, boards, models."""
from __future__ import annotations

import os
from typing import Any

import yaml

_DEFAULT = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                        "config", "prodi.yaml")


def load_config(path: str | None = None) -> dict[str, Any]:
    with open(path or _DEFAULT, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)
