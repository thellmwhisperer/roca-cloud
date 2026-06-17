"""MCP-first contract for Roca Cloud."""
from __future__ import annotations

import json
from typing import Any, Callable

MCP_VERSION = "2025-06-18"
SERVER_INFO = {"name": "roca-cloud", "version": "0.1.0"}

GetService = Callable[[], Any]


def dispatch(request: dict[str, Any], get_service: GetService) -> dict[str, Any]:
    request_id = request.get("id")
    method = request.get("method")
    params = request.get("params") or {}

    try:
        if method == "initialize":
            return _result(request_id, initialize(params.get("protocolVersion")))
        if method == "notifications/initialized":
            return _result(request_id, {})
        if method == "ping":
            return _result(request_id, {})
        if method == "tools/list":
            return _result(request_id, {"tools": tools()})
        if method == "tools/call":
            return _result(request_id, call_tool(get_service(), params))
        if method == "resources/list":
            return _result(request_id, {"resources": resources(get_service())})
        if method == "resources/read":
            return _result(request_id, read_resource(get_service(), params["uri"]))
        if method == "resources/templates/list":
            return _result(request_id, {"resourceTemplates": resource_templates()})
        if method == "prompts/list":
            return _result(request_id, {"prompts": prompts()})
        if method == "prompts/get":
            return _result(request_id, get_prompt(params["name"], params.get("arguments") or {}))
    except KeyError as exc:
        return _error(request_id, -32602, f"missing required field: {exc.args[0]}")
    except ValueError as exc:
        return _error(request_id, -32602, str(exc))

    return _error(request_id, -32601, f"unsupported method: {method}")


def initialize(requested_version: str | None = None) -> dict[str, Any]:
    return {
        "protocolVersion": requested_version or MCP_VERSION,
        "capabilities": {
            "tools": {},
            "resources": {},
            "prompts": {},
        },
        "serverInfo": SERVER_INFO,
    }


def tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "roca_query",
            "description": "Search active Roca Cloud memories.",
            "inputSchema": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "layer": {"type": "string"},
                    "project": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                    "max_chars": {"type": "integer", "minimum": 100, "maximum": 10000},
                },
            },
        },
        {
            "name": "roca_store",
            "description": "Store a Roca Cloud memory, handoff, question, issue, or curated artifact.",
            "inputSchema": {
                "type": "object",
                "required": ["layer", "content"],
                "properties": {
                    "layer": {"type": "string"},
                    "content": {"type": "string"},
                    "origin": {"type": "string", "enum": ["human", "agent", "cron"]},
                    "source_agent": {"type": "string"},
                    "source_session": {"type": "string"},
                    "source_sequence": {"type": "integer"},
                    "project": {"type": "string"},
                    "status": {"type": "string", "enum": ["active", "pending", "resolved"]},
                    "supersedes": {"type": "integer"},
                    "metadata": {"type": "object"},
                },
            },
        },
        {
            "name": "roca_layers",
            "description": "List Roca Cloud semantic layers, aliases, capabilities, and memory counts.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "roca_health",
            "description": "Check Roca Cloud schema, layer, and memory health.",
            "inputSchema": {"type": "object", "properties": {}},
        },
    ]


def call_tool(service: Any, params: dict[str, Any]) -> dict[str, Any]:
    name = _normalize_tool_name(params.get("name"))
    arguments = params.get("arguments") or {}
    if name == "roca_query":
        result = service.query(arguments)
    elif name == "roca_store":
        result = service.store(arguments)
    elif name == "roca_layers":
        result = service.layers()
    elif name == "roca_health":
        result = service.health()
    else:
        raise ValueError(f"unknown tool: {params.get('name')}")
    return {"content": [{"type": "text", "text": json.dumps(result, default=str)}]}


def resources(service: Any) -> list[dict[str, Any]]:
    items = [
        {
            "uri": "roca://health",
            "name": "Roca Cloud health",
            "description": "Schema, layer, and queue health.",
            "mimeType": "application/json",
        },
        {
            "uri": "roca://layers",
            "name": "Roca Cloud layers",
            "description": "Semantic layer catalog with counts and capabilities.",
            "mimeType": "application/json",
        },
    ]
    for layer in service.layers()["layers"]:
        items.append(
            {
                "uri": f"roca://layers/{layer['name']}",
                "name": f"Roca layer: {layer['name']}",
                "description": layer.get("description") or f"Roca layer {layer['name']}",
                "mimeType": "application/json",
            }
        )
    return items


def read_resource(service: Any, uri: str) -> dict[str, Any]:
    if uri == "roca://health":
        return _resource_content(uri, service.health())
    if uri == "roca://layers":
        return _resource_content(uri, service.layers())
    if uri.startswith("roca://layers/"):
        layer_name = uri.removeprefix("roca://layers/")
        for layer in service.layers()["layers"]:
            if layer["name"] == layer_name:
                return _resource_content(uri, layer)
        raise ValueError(f"unknown layer resource: {uri}")
    raise ValueError(f"unknown resource: {uri}")


def resource_templates() -> list[dict[str, Any]]:
    return [
        {
            "uriTemplate": "roca://layers/{layer}",
            "name": "Roca layer",
            "description": "Read metadata, capabilities, and counts for one semantic layer.",
            "mimeType": "application/json",
        },
        {
            "uriTemplate": "roca://projects/{project}/handoffs/latest",
            "name": "Latest project handoff",
            "description": "Read the latest active handoff for a project.",
            "mimeType": "application/json",
        },
        {
            "uriTemplate": "roca://memories/{id}",
            "name": "Roca memory",
            "description": "Read a specific Roca memory by id.",
            "mimeType": "application/json",
        },
    ]


def prompts() -> list[dict[str, Any]]:
    return [
        {
            "name": "roca.session_bootstrap",
            "description": "Bootstrap an agent session from Roca Cloud context.",
            "arguments": [{"name": "project", "description": "Project key", "required": True}],
        },
        {
            "name": "roca.handoff_write",
            "description": "Write a concise handoff for future agents.",
            "arguments": [{"name": "project", "description": "Project key", "required": True}],
        },
        {
            "name": "roca.memory_routing",
            "description": "Choose the correct Roca layer for a new artifact.",
            "arguments": [],
        },
    ]


def get_prompt(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    project = arguments.get("project", "<project>")
    text_by_name = {
        "roca.session_bootstrap": (
            f"Bootstrap this session for project '{project}' using Roca Cloud. "
            "Read latest handoffs, check open questions/issues, then summarize Frozen/Open/Owner/Next."
        ),
        "roca.handoff_write": (
            f"Write a Roca Cloud handoff for project '{project}'. Include branch/workspace, "
            "changes made, verification, blockers, and concrete next steps."
        ),
        "roca.memory_routing": (
            "Classify the artifact into the right Roca layer. Prefer handoff for continuity, "
            "pattern for validated reusable practice, discovery for hard-won facts, issue for blockers, "
            "question for inbox items, and project for durable project state."
        ),
    }
    if name not in text_by_name:
        raise ValueError(f"unknown prompt: {name}")
    return {
        "description": next(item["description"] for item in prompts() if item["name"] == name),
        "messages": [
            {
                "role": "user",
                "content": {"type": "text", "text": text_by_name[name]},
            }
        ],
    }


def _normalize_tool_name(name: str | None) -> str:
    aliases = {
        "roca.query": "roca_query",
        "roca.store": "roca_store",
        "roca.layers": "roca_layers",
        "roca.health": "roca_health",
    }
    if name is None:
        raise ValueError("tool name is required")
    return aliases.get(name, name)


def _resource_content(uri: str, payload: Any) -> dict[str, Any]:
    return {
        "contents": [
            {
                "uri": uri,
                "mimeType": "application/json",
                "text": json.dumps(payload, default=str),
            }
        ]
    }


def _result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
