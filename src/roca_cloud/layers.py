"""Semantic layer registry for Roca Cloud."""
from __future__ import annotations

import json
from typing import Any

from .resources import read_text


def load_layers() -> list[dict[str, Any]]:
    return json.loads(read_text("layers.json"))


def _by_name() -> dict[str, dict[str, Any]]:
    return {layer["name"]: layer for layer in load_layers()}


def normalize_layer(name: str | None) -> str:
    if not name or not str(name).strip():
        raise ValueError("layer is required")
    candidate = str(name).strip()
    layers = _by_name()
    spec = layers.get(candidate)
    if not spec or not spec.get("ingest_allowed", False):
        raise ValueError(f"layer must be a valid ingest layer, got: {candidate}")
    while spec.get("alias_of"):
        candidate = spec["alias_of"]
        spec = layers[candidate]
    return candidate


def sync_layers_table(db) -> int:
    layers = load_layers()
    with db.transaction():
        for layer in layers:
            db.execute(
                """INSERT INTO layers (
                       name, description, schema_file, access_mode,
                       ingest_allowed, is_coordination, is_classifier_label,
                       alias_of, added_by, deprecated, lifecycle, capabilities,
                       since_version
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?::jsonb, ?)
                   ON CONFLICT(name) DO UPDATE SET
                       description = excluded.description,
                       schema_file = excluded.schema_file,
                       access_mode = excluded.access_mode,
                       ingest_allowed = excluded.ingest_allowed,
                       is_coordination = excluded.is_coordination,
                       is_classifier_label = excluded.is_classifier_label,
                       alias_of = excluded.alias_of,
                       added_by = excluded.added_by,
                       deprecated = excluded.deprecated,
                       lifecycle = excluded.lifecycle,
                       capabilities = excluded.capabilities,
                       since_version = excluded.since_version""",
                [
                    layer["name"],
                    layer["description"],
                    "schema.sql",
                    "read-write",
                    bool(layer["ingest_allowed"]),
                    bool(layer["is_coordination"]),
                    bool(layer["is_classifier_label"]),
                    layer["alias_of"],
                    layer["added_by"],
                    bool(layer["deprecated"]),
                    layer["lifecycle"],
                    json.dumps(layer["capabilities"], sort_keys=True),
                    layer["since_version"],
                ],
            )
        names = [layer["name"] for layer in layers]
        placeholders = ", ".join("?" for _ in names)
        db.execute(f"DELETE FROM layers WHERE name NOT IN ({placeholders})", names)
    return len(layers)
