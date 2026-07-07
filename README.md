# Roca Cloud

[![CI](https://github.com/thellmwhisperer/roca-cloud/actions/workflows/ci.yml/badge.svg)](https://github.com/thellmwhisperer/roca-cloud/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-3776ab?logo=python&logoColor=white)](https://python.org)

**An MCP-native memory and coordination plane for agentic systems.**

Agents are stateless by default — every run starts blind. Roca Cloud gives them
a durable place to look things up (prior handoffs, open questions, validated
patterns, operational learnings) and a place to write down what they learned
so the next agent doesn't relearn it. One memory plane, many agents, across runs
and across tools.

The contract is **MCP-first**: agents speak the Model Context Protocol, discover
tools/resources/prompts, read before they act, and leave a concise handoff after.
Coordination falls out of a shared, queryable substrate instead of brittle chat
history.

## Architecture

![Roca Cloud architecture: agents reach roca.example.com (Cloudflare DNS + ACM TLS), which fronts an API Gateway HTTP API that invokes a single ARM64 Lambda container inside a no-NAT VPC; the Lambda talks to RDS PostgreSQL 16 over TCP 5432 and to Secrets Manager through a VPC endpoint, ships logs to CloudWatch, and is built from an ECR image at deploy time.](docs/architecture.png)

A request walks one path: a client (directly, or through the stdio bridge) hits
`roca.example.com` over HTTPS, Cloudflare resolves it to the API Gateway
HTTP API, which forwards to a single Lambda. The Lambda checks the bearer token,
then dispatches the MCP/JSON-RPC call to the service layer, which reads and writes
PostgreSQL. Nothing but the API Gateway is reachable from the public internet.

**Public endpoint:**

```text
https://roca.example.com/mcp
```

Everything except `GET /health` requires a bearer token.

## Core Model

Roca Cloud stores **memories** in **semantic layers**. A memory is never just a
blob of text — it carries the routing metadata that makes it findable later:
layer, project, origin, source agent, status, supersession, timestamps, and
optional structured metadata.

Core tools:

- `roca_store` — store a memory, handoff, question, issue, or artifact.
- `roca_query` — search active memories.
- `roca_layers` — inspect semantic layers, aliases, capabilities, and counts.
- `roca_health` — check schema, layer, and memory health.

The same surface is discoverable through MCP resources and prompts:

- `resources/list`, `resources/read`, `resources/templates/list`
- `prompts/list`, `prompts/get`

Initial resources:

- `roca://health`
- `roca://layers`
- `roca://layers/{layer}`
- `roca://projects/{project}/handoffs/latest`
- `roca://memories/{id}`

## Agent Identity

Agents should name themselves when they write:

```json
{
  "source_agent": "review-agent"
}
```

Use stable, role-describing identifiers — never personal or machine names:

- `coding-agent`
- `review-agent`
- `research-agent`
- `ci-runner`
- `<provider>-<role>`

This keeps audit trails readable without coupling memory records to whoever
happened to be at the keyboard.

## AWS Architecture

The stack is deliberately small, private, and cheap to tear down:

- **Region / IaC** — `eu-west-2`, AWS CDK (Python).
- **Edge** — Cloudflare DNS → API Gateway HTTP API, the only public surface.
  TLS terminates on an ACM certificate bound to the custom domain.
- **Compute** — Lambda as an ARM64 **container image** (built locally, published
  to ECR by CDK), 512 MB, 30s timeout, pinned inside the VPC.
- **Network** — a VPC with **no NAT gateway**. Lambda and the database sit in
  private-isolated subnets; Lambda reaches Secrets Manager through a VPC
  interface endpoint rather than the open internet. The database security group
  only accepts `5432` from the Lambda security group.
- **Data** — RDS PostgreSQL 16 on `t4g.micro`, Single-AZ, 20 GB, not publicly
  accessible.
- **Secrets** — Secrets Manager holds the generated DB credentials and the API
  tokens. Nothing sensitive is baked into the image or passed as plaintext env.
- **Observability** — CloudWatch Logs with 3-day retention.
- **Cost guardrail** — an optional monthly AWS Budget ($100, alert at 80%).
  Removal policies are `DESTROY` throughout: this is a teardownable demo stack,
  designed for repeatable deployment and teardown.

Roca Cloud is its own durable memory plane. Bedrock and AgentCore workloads can
run around it — as agents, distillers, runners, and observability pipelines — all
reading from and writing to Roca Cloud through MCP.

## Auth

`GET /health` is public so uptime checks stay cheap and simple. Everything else
requires:

```text
Authorization: Bearer <token>
```

Tokens live in Secrets Manager as named entries, e.g.:

- `internal-automation`
- `external-reviewer`
- `ci-runner`

Naming them per client means you can rotate or revoke one credential without
disturbing every other integration.

**Never store tokens, API keys, or credentials inside Roca Cloud memories.**

## MCP Usage

Typical first read:

```json
{
  "query": "latest handoff",
  "project": "aws",
  "limit": 5
}
```

Typical handoff write:

```json
{
  "layer": "handoff",
  "project": "aws",
  "origin": "agent",
  "source_agent": "review-agent",
  "content": "Read the latest handoff, verified the current state, and completed the requested slice. Next: run the smoke test from a fresh session.",
  "metadata": {
    "workflow": "connectivity-test"
  }
}
```

## Stdio Bridge

Some clients don't yet speak authenticated HTTP MCP directly. For those, Roca
Cloud ships a small stdio bridge:

```text
scripts/roca-cloud-mcp-stdio.py
```

It exposes cloud-specific tool names so they don't collide with other Roca MCP
servers running locally:

- `roca_cloud_query`
- `roca_cloud_store`
- `roca_cloud_layers`
- `roca_cloud_health`

Codex example:

```toml
[mcp_servers.roca-cloud]
command = "/path/to/roca-cloud/scripts/roca-cloud-mcp-stdio.py"
enabled = true

[mcp_servers.roca-cloud.env]
ROCA_CLOUD_MCP_URL = "https://roca.example.com/mcp"
ROCA_CLOUD_API_TOKEN = "<token>"

[mcp_servers.roca-cloud.tools.roca_cloud_query]
approval_mode = "approve"

[mcp_servers.roca-cloud.tools.roca_cloud_store]
approval_mode = "approve"

[mcp_servers.roca-cloud.tools.roca_cloud_layers]
approval_mode = "approve"

[mcp_servers.roca-cloud.tools.roca_cloud_health]
approval_mode = "approve"
```

Claude Desktop example:

```json
{
  "mcpServers": {
    "roca-cloud": {
      "command": "/path/to/roca-cloud/.venv/bin/python",
      "args": [
        "/path/to/roca-cloud/scripts/roca-cloud-mcp-stdio.py"
      ],
      "env": {
        "ROCA_CLOUD_MCP_URL": "https://roca.example.com/mcp",
        "ROCA_CLOUD_API_TOKEN": "<token>"
      }
    }
  }
}
```

## Development

```bash
make test       # run the test suite
make synth      # synthesize the CDK stack
make deploy     # deploy to AWS
make outputs    # show stack outputs
make destroy    # tear the demo stack down

ROCA_CLOUD_API_TOKEN=<token> make smoke   # smoke-test the live endpoint
```

## Agent Workflow

The intended loop is a multi-agent working memory:

1. An agent does work in some external system.
2. It writes a handoff into Roca Cloud.
3. A reviewer or follow-up agent reads that handoff.
4. The next agent continues with durable context instead of leaning on chat
   history.
5. Distillation jobs later turn logs, tool use, PRs, and handoffs into curated
   knowledge.

That's the whole point: agents get to talk to **what happened before**, not just
to the current prompt.
