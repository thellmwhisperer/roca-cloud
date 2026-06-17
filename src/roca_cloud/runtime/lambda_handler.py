"""API Gateway/Lambda adapter for Roca Cloud."""
from __future__ import annotations

import json
from typing import Any

from roca_cloud.mcp import contract as mcp_contract
from roca_cloud.runtime import auth
from roca_cloud.service import RocaCloudService

_SERVICE: RocaCloudService | None = None


def _service() -> RocaCloudService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = RocaCloudService()
        _SERVICE.connect()
    return _SERVICE


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    try:
        if _requires_auth(event) and not auth.is_authorized(event):
            return _response(
                401,
                {"error": "unauthorized"},
                headers={"www-authenticate": "Bearer"},
            )
        return _response(200, _dispatch(event))
    except KeyError as exc:
        return _response(400, {"error": f"missing required field: {exc.args[0]}"})
    except ValueError as exc:
        return _response(400, {"error": str(exc)})
    except Exception as exc:  # pragma: no cover - Lambda safety boundary
        return _response(500, {"error": str(exc)})


def _dispatch(event: dict[str, Any]) -> Any:
    path = event.get("rawPath") or event.get("path") or "/"
    method = (
        event.get("requestContext", {})
        .get("http", {})
        .get("method", event.get("httpMethod", "GET"))
        .upper()
    )
    body = _body(event)

    if method == "GET" and path == "/health":
        return _service().health()
    if method == "GET" and path == "/layers":
        return _service().layers()
    if method == "POST" and path == "/tools/roca_store":
        return _service().store(body)
    if method == "POST" and path == "/tools/roca_query":
        return _service().query(body)
    if method == "POST" and path == "/tools/roca_layers":
        return _service().layers()
    if method == "POST" and path == "/tools/roca_health":
        return _service().health()
    if method == "POST" and path == "/mcp":
        return mcp_contract.dispatch(body, _service)
    return {"error": "not found", "path": path, "method": method}


def _requires_auth(event: dict[str, Any]) -> bool:
    if not auth.auth_configured():
        return False
    path = event.get("rawPath") or event.get("path") or "/"
    method = (
        event.get("requestContext", {})
        .get("http", {})
        .get("method", event.get("httpMethod", "GET"))
        .upper()
    )
    return not (method == "GET" and path == "/health")


def _body(event: dict[str, Any]) -> dict[str, Any]:
    raw = event.get("body")
    if not raw:
        return {}
    if event.get("isBase64Encoded"):
        import base64

        raw = base64.b64decode(raw).decode("utf-8")
    return json.loads(raw)


def _response(
    status: int,
    body: Any,
    *,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    response_headers = {"content-type": "application/json"}
    if headers:
        response_headers.update(headers)
    return {
        "statusCode": status,
        "headers": response_headers,
        "body": json.dumps(body, default=str),
    }
