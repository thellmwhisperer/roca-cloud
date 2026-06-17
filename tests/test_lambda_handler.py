import json
import os
import unittest
from unittest import mock

from roca_cloud.runtime import auth
from roca_cloud.runtime import lambda_handler


class FakeService:
    def health(self):
        return {"ok": True}

    def layers(self):
        return {"layers": []}

    def store(self, payload):
        return {"id": 1, "payload": payload}

    def query(self, payload):
        return {"rows": [], "query": payload["query"]}


class LambdaHandlerTest(unittest.TestCase):
    def setUp(self):
        lambda_handler._SERVICE = FakeService()
        auth.clear_cache()

    def tearDown(self):
        lambda_handler._SERVICE = None
        auth.clear_cache()

    def test_health_route(self):
        response = lambda_handler.handler(
            {"rawPath": "/health", "requestContext": {"http": {"method": "GET"}}},
            None,
        )
        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(json.loads(response["body"]), {"ok": True})

    def test_mcp_tool_call(self):
        response = lambda_handler.handler(
            {
                "rawPath": "/mcp",
                "requestContext": {"http": {"method": "POST"}},
                "body": json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "roca_store",
                            "arguments": {"layer": "handoff", "content": "hello"},
                        },
                    }
                ),
            },
            None,
        )
        body = json.loads(response["body"])
        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(body["jsonrpc"], "2.0")
        self.assertEqual(body["id"], 1)
        self.assertIn("content", body["result"])

    def test_mcp_initialize(self):
        response = lambda_handler.handler(
            {
                "rawPath": "/mcp",
                "requestContext": {"http": {"method": "POST"}},
                "body": json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {},
                            "clientInfo": {"name": "probe", "version": "1"},
                        },
                    }
                ),
            },
            None,
        )
        body = json.loads(response["body"])
        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(body["result"]["serverInfo"]["name"], "roca-cloud")
        self.assertEqual(body["result"]["protocolVersion"], "2024-11-05")

    def test_mcp_tools_list_includes_input_schema(self):
        response = lambda_handler.handler(
            {
                "rawPath": "/mcp",
                "requestContext": {"http": {"method": "POST"}},
                "body": json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
            },
            None,
        )
        body = json.loads(response["body"])
        tools = body["result"]["tools"]
        self.assertIn("inputSchema", tools[0])

    def test_mcp_initialize_does_not_touch_database_service(self):
        lambda_handler._SERVICE = None
        response = lambda_handler.handler(
            {
                "rawPath": "/mcp",
                "requestContext": {"http": {"method": "POST"}},
                "body": json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 10,
                        "method": "initialize",
                        "params": {"protocolVersion": "2025-06-18"},
                    }
                ),
            },
            None,
        )
        body = json.loads(response["body"])
        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(body["result"]["serverInfo"]["name"], "roca-cloud")

    def test_mcp_resources_read_route(self):
        response = lambda_handler.handler(
            {
                "rawPath": "/mcp",
                "requestContext": {"http": {"method": "POST"}},
                "body": json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 11,
                        "method": "resources/read",
                        "params": {"uri": "roca://layers"},
                    }
                ),
            },
            None,
        )
        body = json.loads(response["body"])
        self.assertEqual(response["statusCode"], 200)
        self.assertIn("contents", body["result"])

    def test_mcp_requires_bearer_token_when_auth_is_configured(self):
        with mock.patch.dict(os.environ, {"ROCA_AUTH_TOKENS": "edu-secret"}, clear=False):
            auth.clear_cache()
            response = lambda_handler.handler(
                {
                    "rawPath": "/mcp",
                    "requestContext": {"http": {"method": "POST"}},
                    "body": json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
                },
                None,
            )
        body = json.loads(response["body"])
        self.assertEqual(response["statusCode"], 401)
        self.assertEqual(body["error"], "unauthorized")

    def test_mcp_accepts_bearer_token_when_auth_is_configured(self):
        with mock.patch.dict(os.environ, {"ROCA_AUTH_TOKENS": "edu-secret"}, clear=False):
            auth.clear_cache()
            response = lambda_handler.handler(
                {
                    "rawPath": "/mcp",
                    "requestContext": {"http": {"method": "POST"}},
                    "headers": {"authorization": "Bearer edu-secret"},
                    "body": json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
                },
                None,
            )
        body = json.loads(response["body"])
        self.assertEqual(response["statusCode"], 200)
        self.assertIn("tools", body["result"])

    def test_health_stays_public_when_auth_is_configured(self):
        with mock.patch.dict(os.environ, {"ROCA_AUTH_TOKENS": "edu-secret"}, clear=False):
            auth.clear_cache()
            response = lambda_handler.handler(
                {"rawPath": "/health", "requestContext": {"http": {"method": "GET"}}},
                None,
            )
        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(json.loads(response["body"]), {"ok": True})


if __name__ == "__main__":
    unittest.main()
