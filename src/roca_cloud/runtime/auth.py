"""Bearer-token auth for the public Roca Cloud edge."""
from __future__ import annotations

import hmac
import json
import os
from typing import Any

_TOKEN_CACHE: list[str] | None = None


def clear_cache() -> None:
    global _TOKEN_CACHE
    _TOKEN_CACHE = None


def auth_configured() -> bool:
    return bool(os.environ.get("ROCA_AUTH_TOKENS") or os.environ.get("ROCA_AUTH_TOKEN_SECRET_ARN"))


def is_authorized(event: dict[str, Any]) -> bool:
    tokens = _accepted_tokens()
    if not tokens:
        return True

    provided = _provided_token(event)
    if not provided:
        return False
    return any(hmac.compare_digest(provided, token) for token in tokens)


def _provided_token(event: dict[str, Any]) -> str | None:
    headers = event.get("headers") or {}
    normalized = {str(key).lower(): str(value) for key, value in headers.items()}
    authorization = normalized.get("authorization")
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token:
            return token.strip()
        return authorization.strip()
    api_key = normalized.get("x-api-key")
    if api_key:
        return api_key.strip()
    return None


def _accepted_tokens() -> list[str]:
    global _TOKEN_CACHE
    if _TOKEN_CACHE is not None:
        return _TOKEN_CACHE

    values: list[str] = []
    inline_tokens = os.environ.get("ROCA_AUTH_TOKENS")
    if inline_tokens:
        values.extend(_parse_secret_value(inline_tokens))

    secret_arn = os.environ.get("ROCA_AUTH_TOKEN_SECRET_ARN")
    if secret_arn:
        values.extend(_load_secret_tokens(secret_arn))

    _TOKEN_CACHE = [token for token in values if token]
    return _TOKEN_CACHE


def _load_secret_tokens(secret_arn: str) -> list[str]:
    import boto3  # Available in the AWS Lambda Python base runtime.

    response = boto3.client("secretsmanager").get_secret_value(SecretId=secret_arn)
    return _parse_secret_value(response["SecretString"])


def _parse_secret_value(value: str) -> list[str]:
    stripped = value.strip()
    if not stripped:
        return []
    if not stripped.startswith(("{", "[")):
        return [item.strip() for item in stripped.split(",") if item.strip()]

    parsed = json.loads(stripped)
    return _flatten_token_values(parsed)


def _flatten_token_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        tokens: list[str] = []
        for item in value:
            tokens.extend(_flatten_token_values(item))
        return tokens
    if isinstance(value, dict):
        tokens: list[str] = []
        for item in value.values():
            tokens.extend(_flatten_token_values(item))
        return tokens
    return []
