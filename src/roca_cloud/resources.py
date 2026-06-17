"""Package resource helpers."""
from __future__ import annotations

from importlib import resources


def read_text(name: str) -> str:
    return resources.files("roca_cloud.data").joinpath(name).read_text(encoding="utf-8")
