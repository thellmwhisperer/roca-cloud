import json
import unittest

from roca_cloud.mcp import contract


class FakeService:
    def health(self):
        return {"ok": True}

    def layers(self):
        return {
            "layers": [
                {"name": "handoff", "description": "Session continuity", "row_count": 2},
                {"name": "pattern", "description": "Validated practice", "row_count": 1},
            ]
        }

    def store(self, payload):
        return {"id": 42, "payload": payload}

    def query(self, payload):
        return {"rows": [{"id": 1, "content": "hello"}], "query": payload["query"]}


class McpContractTest(unittest.TestCase):
    def setUp(self):
        self.service = FakeService()

    def dispatch(self, request):
        return contract.dispatch(request, lambda: self.service)

    def test_initialize_advertises_tools_resources_and_prompts(self):
        response = self.dispatch(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18"},
            }
        )
        result = response["result"]
        self.assertEqual(result["serverInfo"]["name"], "roca-cloud")
        self.assertIn("tools", result["capabilities"])
        self.assertIn("resources", result["capabilities"])
        self.assertIn("prompts", result["capabilities"])

    def test_tools_list_discovers_roca_core_tools_with_schemas(self):
        response = self.dispatch({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = {tool["name"]: tool for tool in response["result"]["tools"]}

        self.assertIn("roca_query", tools)
        self.assertIn("roca_store", tools)
        self.assertIn("roca_layers", tools)
        self.assertIn("roca_health", tools)
        self.assertEqual(tools["roca_query"]["inputSchema"]["required"], ["query"])
        self.assertEqual(tools["roca_store"]["inputSchema"]["required"], ["layer", "content"])

    def test_resources_list_exposes_layers_as_mcp_resources(self):
        response = self.dispatch({"jsonrpc": "2.0", "id": 3, "method": "resources/list"})
        resources = {resource["uri"]: resource for resource in response["result"]["resources"]}

        self.assertIn("roca://layers", resources)
        self.assertIn("roca://layers/handoff", resources)
        self.assertEqual(resources["roca://layers"]["mimeType"], "application/json")

    def test_resources_read_layers_returns_json_content(self):
        response = self.dispatch(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "resources/read",
                "params": {"uri": "roca://layers/handoff"},
            }
        )
        content = response["result"]["contents"][0]
        self.assertEqual(content["uri"], "roca://layers/handoff")
        self.assertEqual(content["mimeType"], "application/json")
        self.assertEqual(json.loads(content["text"])["name"], "handoff")

    def test_resource_templates_are_discoverable(self):
        response = self.dispatch({"jsonrpc": "2.0", "id": 5, "method": "resources/templates/list"})
        templates = {template["uriTemplate"] for template in response["result"]["resourceTemplates"]}
        self.assertIn("roca://layers/{layer}", templates)
        self.assertIn("roca://projects/{project}/handoffs/latest", templates)

    def test_prompts_are_discoverable_and_renderable(self):
        listed = self.dispatch({"jsonrpc": "2.0", "id": 6, "method": "prompts/list"})
        prompts = {prompt["name"] for prompt in listed["result"]["prompts"]}
        self.assertIn("roca.session_bootstrap", prompts)

        rendered = self.dispatch(
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "prompts/get",
                "params": {
                    "name": "roca.session_bootstrap",
                    "arguments": {"project": "aws"},
                },
            }
        )
        message = rendered["result"]["messages"][0]
        self.assertEqual(message["role"], "user")
        self.assertIn("aws", message["content"]["text"])


if __name__ == "__main__":
    unittest.main()
