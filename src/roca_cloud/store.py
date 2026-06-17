"""Store contract for Roca Cloud memories."""
from __future__ import annotations

import json
from typing import Any

from .layers import normalize_layer

VALID_ORIGINS = {"human", "agent", "cron"}
VALID_STATUSES = {"active", "pending", "resolved"}


def roca_store(
    db,
    *,
    layer: str,
    content: str,
    origin: str = "agent",
    source_agent: str | None = None,
    source_session: str | None = None,
    source_sequence: int | None = None,
    project: str | None = None,
    status: str = "active",
    supersedes: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if origin not in VALID_ORIGINS:
        raise ValueError(f"origin must be one of: {', '.join(sorted(VALID_ORIGINS))}")
    if status not in VALID_STATUSES:
        raise ValueError(f"status must be one of: {', '.join(sorted(VALID_STATUSES))}")
    if not content or not content.strip():
        raise ValueError("content is required")

    normalized_layer = normalize_layer(layer)
    trimmed = content.strip()
    existing = db.query(
        """SELECT id
           FROM memories
           WHERE supersedes IS NULL
             AND content = ?
             AND project IS NOT DISTINCT FROM ?
           LIMIT 1""",
        [trimmed, project],
    )
    if existing:
        return {"id": int(existing[0]["id"]), "skipped": True}

    row_id = db.insert_returning_id(
        """INSERT INTO memories (
               layer, content, metadata, origin, source_agent,
               source_session, source_sequence, project, status, supersedes
           ) VALUES (?, ?, ?::jsonb, ?, ?, ?, ?, ?, ?, ?)""",
        [
            normalized_layer,
            trimmed,
            json.dumps(metadata or {}, sort_keys=True),
            origin,
            source_agent,
            source_session,
            source_sequence,
            project,
            status,
            supersedes,
        ],
    )
    return {"id": int(row_id), "skipped": False}
