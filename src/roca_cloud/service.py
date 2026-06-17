"""Application service layer for the Roca Cloud Lambda runtime."""
from __future__ import annotations

import os
import json
from typing import Any

from .db import PostgresDb
from .layers import sync_layers_table
from .resources import read_text
from .store import roca_store


class RocaCloudService:
    def __init__(self, db=None):
        self.db = db or PostgresDb(_database_url_from_env())
        self._ready = False

    def connect(self) -> None:
        if hasattr(self.db, "connect"):
            self.db.connect()

    def close(self) -> None:
        if hasattr(self.db, "close"):
            self.db.close()

    def ensure_schema(self) -> None:
        if self._ready:
            return
        self.db.execute_script(read_text("schema.sql"))
        sync_layers_table(self.db)
        self._ready = True

    def store(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.ensure_schema()
        return roca_store(
            self.db,
            layer=payload["layer"],
            content=payload["content"],
            origin=payload.get("origin", "agent"),
            source_agent=payload.get("source_agent"),
            source_session=payload.get("source_session"),
            source_sequence=payload.get("source_sequence"),
            project=payload.get("project"),
            status=payload.get("status", "active"),
            supersedes=payload.get("supersedes"),
            metadata=payload.get("metadata") or {},
        )

    def layers(self) -> dict[str, Any]:
        self.ensure_schema()
        rows = self.db.query(
            """SELECT l.name, l.description, l.ingest_allowed, l.is_coordination,
                      l.is_classifier_label, l.alias_of, l.added_by, l.deprecated,
                      l.lifecycle, l.capabilities, l.since_version,
                      COUNT(m.id) AS row_count,
                      COALESCE(SUM(CASE WHEN m.id IS NOT NULL AND m.supersedes IS NULL THEN 1 ELSE 0 END), 0)
                        AS active_count
               FROM layers l
               LEFT JOIN memories m ON m.layer = l.name
               GROUP BY l.name
               ORDER BY l.name"""
        )
        return {"layers": rows}

    def health(self) -> dict[str, Any]:
        self.ensure_schema()
        memory_count = self.db.query("SELECT COUNT(*) AS count FROM memories")[0]["count"]
        layer_count = self.db.query("SELECT COUNT(*) AS count FROM layers")[0]["count"]
        unresolved = self.db.query(
            """SELECT COUNT(*) AS count
               FROM memories
               WHERE status = 'pending'"""
        )[0]["count"]
        return {
            "ok": True,
            "checks": {
                "schema": "ready",
                "layers": int(layer_count),
                "memories": int(memory_count),
                "pending": int(unresolved),
            },
        }

    def query(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.ensure_schema()
        query = str(payload.get("query") or "").strip()
        layer = payload.get("layer")
        project = payload.get("project")
        limit = int(payload.get("limit") or 10)
        max_chars = int(payload.get("max_chars") or 800)
        if not query:
            raise ValueError("query is required")

        where = ["supersedes IS NULL", "content ILIKE ?"]
        params: list[Any] = [f"%{query}%"]
        if layer:
            where.append("layer = ?")
            params.append(layer)
        if project:
            where.append("project = ?")
            params.append(project)
        params.append(limit)
        rows = self.db.query(
            f"""SELECT id, layer, project, origin, source_agent, status,
                       LEFT(content, {max_chars}) AS content,
                       created_at
                FROM memories
                WHERE {' AND '.join(where)}
                ORDER BY created_at DESC
                LIMIT ?""",
            params,
        )
        return {"rows": rows, "path": "postgres_ilike", "query": query}


def _database_url_from_env() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    secret = _db_secret()
    host = os.environ["DB_HOST"]
    port = os.environ.get("DB_PORT", "5432")
    name = os.environ.get("DB_NAME", "roca")
    user = os.environ.get("DB_USER") or secret["username"]
    password = os.environ.get("DB_PASSWORD") or secret["password"]
    return f"postgresql://{user}:{password}@{host}:{port}/{name}"


def _db_secret() -> dict[str, str]:
    password = os.environ.get("DB_PASSWORD")
    user = os.environ.get("DB_USER")
    if password and user:
        return {"username": user, "password": password}

    secret_arn = os.environ.get("DB_SECRET_ARN")
    if not secret_arn:
        return {}

    import boto3  # Available in the AWS Lambda Python base runtime.

    response = boto3.client("secretsmanager").get_secret_value(SecretId=secret_arn)
    return json.loads(response["SecretString"])
