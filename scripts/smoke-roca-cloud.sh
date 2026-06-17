#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-$HOME/aws}"
PROFILE="${AWS_PROFILE:-default}"
REGION="${AWS_REGION:-eu-west-2}"
STACK_NAME="${STACK_NAME:-RocaCloudStack}"

export PATH="$ROOT/.tools/bin:/Applications/Docker.app/Contents/Resources/bin:$PATH"
export AWS_CONFIG_FILE="$ROOT/.aws/config"
export AWS_SHARED_CREDENTIALS_FILE="$ROOT/.aws/credentials"

api_url="$(
  aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --profile "$PROFILE" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`RocaApiUrl`].OutputValue | [0]' \
    --output text
)"

echo "API: $api_url"

auth_header=()
if [[ -n "${ROCA_CLOUD_API_TOKEN:-}" ]]; then
  auth_header=(-H "authorization: Bearer ${ROCA_CLOUD_API_TOKEN}")
fi

echo
echo "health:"
curl -fsS "$api_url/health"
echo
echo
echo "store:"
curl -fsS \
  -X POST "$api_url/tools/roca_store" \
  "${auth_header[@]}" \
  -H 'content-type: application/json' \
  -d '{"layer":"handoff","content":"hello world from the roca-cloud smoke test","project":"aws","source_agent":"Codex","metadata":{"demo":"roca-cloud-smoke"}}'
echo
echo
echo "query:"
curl -fsS \
  -X POST "$api_url/tools/roca_query" \
  "${auth_header[@]}" \
  -H 'content-type: application/json' \
  -d '{"query":"hola mundo","project":"aws","limit":3}'
echo
echo
echo "mcp initialize:"
curl -fsS \
  -X POST "$api_url/mcp" \
  "${auth_header[@]}" \
  -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoke","version":"1"}}}'
echo
echo
echo "mcp resources/templates/list:"
curl -fsS \
  -X POST "$api_url/mcp" \
  "${auth_header[@]}" \
  -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":2,"method":"resources/templates/list"}'
echo
echo
echo "mcp prompts/list:"
curl -fsS \
  -X POST "$api_url/mcp" \
  "${auth_header[@]}" \
  -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":3,"method":"prompts/list"}'
echo
