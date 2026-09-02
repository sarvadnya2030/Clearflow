#!/usr/bin/env bash
# ClearFlow Vault KV-v2 secret seeding script
# Idempotent: safe to run multiple times — it updates existing secrets in place
# Prerequisites: vault CLI in PATH, VAULT_ADDR and VAULT_TOKEN env vars set
#   source infrastructure/vault/.env.local   (never commit that file)
#
# Usage:
#   export VAULT_ADDR=http://localhost:8200
#   export VAULT_TOKEN=$(cat infrastructure/vault/.vault-token)
#   bash infrastructure/vault/scripts/seed-secrets.sh

set -euo pipefail

VAULT_ADDR="${VAULT_ADDR:-http://localhost:8200}"
VAULT_TOKEN="${VAULT_TOKEN:?VAULT_TOKEN must be set}"

echo "[seed-secrets] Connecting to Vault at $VAULT_ADDR"
vault status --format=json | jq -r '.initialized, .sealed' || { echo "ERROR: Cannot connect to Vault"; exit 1; }

# Enable KV-v2 engine if not already enabled
if ! vault secrets list -format=json | jq -r 'keys[]' | grep -q "^clearflow/"; then
  echo "[seed-secrets] Enabling KV-v2 at clearflow/"
  vault secrets enable -path=clearflow -version=2 kv
fi

# ── Helper: write secret if value is provided, else skip ──────────────────────
put() {
  local path="$1"; shift
  echo "[seed-secrets] Writing $path"
  vault kv put "$path" "$@"
}

# ── Gateway ───────────────────────────────────────────────────────────────────
put clearflow/gateway/redis \
  password="${GATEWAY_REDIS_PASSWORD:-clearflow123}"

put clearflow/gateway/artemis \
  username="${GATEWAY_ARTEMIS_USER:-clearflow}" \
  password="${GATEWAY_ARTEMIS_PASSWORD:-clearflow123}"

put clearflow/gateway/jwt \
  secret="${GATEWAY_JWT_SECRET:-replace-me-with-32-char-min-secret}"

# ── Fraud Scoring ─────────────────────────────────────────────────────────────
put clearflow/fraud-scoring/redis \
  password="${FRAUD_REDIS_PASSWORD:-clearflow123}"

# ── AML Compliance ────────────────────────────────────────────────────────────
put clearflow/aml-compliance/mongodb \
  uri="${AML_MONGODB_URI:-mongodb://localhost:27017/clearflow}" \
  password="${AML_MONGODB_PASSWORD:-}"

put clearflow/aml-compliance/redis \
  password="${AML_REDIS_PASSWORD:-clearflow123}"

# ── Settlement ────────────────────────────────────────────────────────────────
put clearflow/settlement/datasource \
  url="${SETTLEMENT_DB_URL:-jdbc:h2:mem:settlement}" \
  password="${SETTLEMENT_DB_PASSWORD:-}"

put clearflow/settlement/artemis \
  username="${SETTLEMENT_ARTEMIS_USER:-clearflow}" \
  password="${SETTLEMENT_ARTEMIS_PASSWORD:-clearflow123}"

put clearflow/settlement/redis \
  password="${SETTLEMENT_REDIS_PASSWORD:-clearflow123}"

# ── Audit ─────────────────────────────────────────────────────────────────────
put clearflow/audit/cassandra \
  password="${AUDIT_CASSANDRA_PASSWORD:-}"

put clearflow/audit/redis \
  password="${AUDIT_REDIS_PASSWORD:-clearflow123}"

# ── MCP Gateway ───────────────────────────────────────────────────────────────
put clearflow/mcp-readonly-gateway/jwt \
  secret="${MCP_JWT_SECRET:-replace-me-with-32-char-min-secret}"

put clearflow/mcp-readonly-gateway/elasticsearch \
  password="${MCP_ES_PASSWORD:-}"

echo ""
echo "[seed-secrets] ✓ All secrets written to Vault KV-v2 at path clearflow/"
echo "[seed-secrets] Next: restart services with spring.cloud.vault.enabled=true"
