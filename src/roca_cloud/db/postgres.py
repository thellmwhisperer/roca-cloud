"""PostgreSQL database adapter for Roca Cloud."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import re
import threading
from typing import Any, Iterable

_DOLLAR_PARAM_RE = re.compile(r"\$(\d+)")


def translate_params(sql: str, params: Iterable[Any] | None = None) -> tuple[str, list[Any]]:
    """Translate Roca's mixed placeholder style to psycopg `%s`.

    Local Roca code historically emits both SQLite-style `?` placeholders and
    PostgreSQL-style `$1` placeholders. Psycopg expects `%s`; this scanner keeps
    placeholders inside string literals untouched and preserves `$n` reuse.
    """
    source = list(params or [])
    translated: list[str] = []
    ordered: list[Any] = []
    qmark_idx = 0
    i = 0
    in_single_quote = False

    while i < len(sql):
        char = sql[i]

        if char == "'":
            translated.append(char)
            if in_single_quote and i + 1 < len(sql) and sql[i + 1] == "'":
                translated.append("'")
                i += 2
                continue
            in_single_quote = not in_single_quote
            i += 1
            continue

        if in_single_quote:
            translated.append(char)
            i += 1
            continue

        if char == "?":
            if qmark_idx >= len(source):
                raise ValueError("Missing parameter for ? placeholder")
            ordered.append(source[qmark_idx])
            qmark_idx += 1
            translated.append("%s")
            i += 1
            continue

        if char == "$":
            match = _DOLLAR_PARAM_RE.match(sql, i)
            if match:
                idx = int(match.group(1)) - 1
                if idx < 0 or idx >= len(source):
                    raise ValueError(f"Missing parameter for {match.group(0)}")
                ordered.append(source[idx])
                translated.append("%s")
                i = match.end()
                continue

        translated.append(char)
        i += 1

    if not ordered and source:
        ordered = source
    return "".join(translated), ordered


@dataclass
class _Transaction:
    rolled_back: bool = False

    def rollback(self) -> None:
        self.rolled_back = True


class PostgresDb:
    """Small psycopg adapter with the same public seam as local Roca's DB."""

    def __init__(self, dsn: str):
        self._dsn = dsn
        self._conn = None
        self._lock = threading.Lock()
        self._local = threading.local()

    def connect(self) -> None:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover - deployment dependency
            raise RuntimeError("psycopg[binary] is required for PostgresDb") from exc

        self._conn = psycopg.connect(self._dsn, row_factory=dict_row)
        self._conn.autocommit = True

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _connection(self):
        tx_conn = getattr(self._local, "tx_conn", None)
        return tx_conn or self._conn

    def execute_script(self, sql: str) -> None:
        with self._lock:
            with self._conn.cursor() as cur:
                cur.execute(sql)

    def query(self, sql: str, params: Iterable[Any] | None = None) -> list[dict[str, Any]]:
        translated, ordered = translate_params(sql, params)
        conn = self._connection()
        with conn.cursor() as cur:
            cur.execute(translated, ordered)
            if cur.description is None:
                return []
            return [dict(row) for row in cur.fetchall()]

    def execute(self, sql: str, params: Iterable[Any] | None = None) -> None:
        translated, ordered = translate_params(sql, params)
        conn = self._connection()
        with conn.cursor() as cur:
            cur.execute(translated, ordered)

    def insert_returning_id(self, sql: str, params: Iterable[Any] | None = None) -> int:
        statement = sql.strip().rstrip(";")
        if " returning " not in statement.lower():
            statement = f"{statement} RETURNING id"
        rows = self.query(statement, params)
        if not rows:
            raise RuntimeError("INSERT did not return an id")
        return int(rows[0]["id"])

    @contextmanager
    def transaction(self):
        if getattr(self._local, "tx_conn", None) is not None:
            raise RuntimeError("Nested transaction() is not supported")
        tx = _Transaction()
        with self._lock:
            self._conn.execute("BEGIN")
            self._local.tx_conn = self._conn
            try:
                yield tx
                if tx.rolled_back:
                    self._conn.rollback()
                else:
                    self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
            finally:
                self._local.tx_conn = None
