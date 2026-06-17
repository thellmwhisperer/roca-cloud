#!/usr/bin/env python3
"""Stdio MCP bridge for Roca Cloud.

Codex and Claude Desktop can launch this as a local stdio MCP server. The
bridge forwards tool calls to the deployed Roca Cloud HTTP JSON-RPC endpoint.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any


DEFAULT_ROCA_CLOUD_URL = "https://roca.example.com/mcp"
ROCA_CLOUD_URL = os.environ.get("ROCA_CLOUD_MCP_URL", DEFAULT_ROCA_CLOUD_URL)
ROCA_CLOUD_API_TOKEN = os.environ.get("ROCA_CLOUD_API_TOKEN")

REMOTE_TOOL_BY_LOCAL = {
    "roca_cloud_store": "roca_store",
    "roca_cloud_query": "roca_query",
    "roca_cloud_layers": "roca_layers",
    "roca_cloud_health": "roca_health",
}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = dispatch(request)
        except Exception as exc:  # Keep the stdio server alive on bad input.
            response = error_response(None, -32603, str(exc))
        if response is not None:
            write(response)


def dispatch(request: dict[str, Any]) -> dict[str, Any] | None:
    method = request.get("method")
    request_id = request.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "roca-cloud", "version": "0.1.0"},
            },
        }

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"tools": tools()},
        }

    if method == "tools/call":
        params = request.get("params") or {}
        local_name = params.get("name")
        arguments = params.get("arguments") or {}
        remote_name = REMOTE_TOOL_BY_LOCAL.get(local_name)
        if remote_name is None:
            return error_response(request_id, -32602, f"unknown tool: {local_name}")
        result = call_remote(remote_name, arguments)
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    return error_response(request_id, -32601, f"unsupported method: {method}")


def call_remote(remote_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": remote_name, "arguments": arguments},
    }
    req = urllib.request.Request(
        ROCA_CLOUD_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=_headers(),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Roca Cloud HTTP {exc.code}: {detail}") from exc
    if "error" in body:
        raise RuntimeError(json.dumps(body["error"]))
    return body["result"]


def _headers() -> dict[str, str]:
    headers = {"content-type": "application/json"}
    if ROCA_CLOUD_API_TOKEN:
        headers["authorization"] = f"Bearer {ROCA_CLOUD_API_TOKEN}"
    return headers


def tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "roca_cloud_store",
            "description": "Store a Roca Cloud memory or handoff in the AWS PostgreSQL-backed Roca.",
            "inputSchema": {
                "type": "object",
                "required": ["layer", "content"],
                "properties": {
                    "layer": {"type": "string"},
                    "content": {"type": "string"},
                    "project": {"type": "string"},
                    "origin": {"type": "string"},
                    "source_agent": {"type": "string"},
                    "metadata": {"type": "object"},
                },
            },
        },
        {
            "name": "roca_cloud_query",
            "description": "Search active memories in Roca Cloud.",
            "inputSchema": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "project": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                },
            },
        },
        {
            "name": "roca_cloud_layers",
            "description": "List Roca Cloud semantic layers and memory counts.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "roca_cloud_health",
            "description": "Check Roca Cloud schema, layer, and memory health.",
            "inputSchema": {"type": "object", "properties": {}},
        },
    ]


def error_response(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def write(response: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(response) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
