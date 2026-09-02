#!/bin/bash
# Vault dev-mode initialiser for ClearFlow
# Idempotent: safe to run multiple times
# Usage: bash vault-init.sh [--quiet]

QUIET=false
[[ "$1" == "--quiet" ]] && QUIET=true

log() { $QUIET || echo "$@"; }

VAULT_ADDR="${VAULT_ADDR:-http://localhost:8200}"
# In dev mode, the root token is always "root"
VAULT_TOKEN="${VAULT_TOKEN:-root}"

export VAULT_ADDR VAULT_TOKEN

# ── Wait for vault to be ready (max 30s) ─────────────────────────────────────
log "  [vault] Waiting for Vault at $VAULT_ADDR..."
for i in $(seq 1 10); do
  if curl -sf "$VAULT_ADDR/v1/sys/health" &>/dev/null; then
    log "  [vault] Vault ready."
    break
  fi
  sleep 3
  if [ "$i" -eq 10 ]; then
    echo "  [vault] ⚠️  Vault not reachable after 30s — skipping secret seed"
    exit 1
  fi
done

# Check if vault is running in dev mode (already unsealed)
STATUS=$(curl -sf "$VAULT_ADDR/v1/sys/health" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('sealed','unknown'))" 2>/dev/null || echo "unknown")
if [ "$STATUS" = "True" ] || [ "$STATUS" = "true" ]; then
  echo "  [vault] Vault is sealed — skipping (requires manual unseal in prod mode)"
  exit 0
fi

# ── Enable KV-v2 (idempotent) ─────────────────────────────────────────────────
curl -sf --header "X-Vault-Token: $VAULT_TOKEN" \
     --request POST \
     --data '{"type":"kv","options":{"version":"2"}}' \
     "$VAULT_ADDR/v1/sys/mounts/secret" &>/dev/null || true

log "  [vault] KV-v2 mounted at secret/"

# ── Seed secrets ─────────────────────────────────────────────────────────────
seed() {
  local path=$1; shift
  local data="{}"
  for kv in "$@"; do
    key="${kv%%=*}"; val="${kv#*=}"
    data=$(echo "$data" | python3 -c "
import sys, json
d = json.load(sys.stdin)
d['${key}'] = '${val}'
print(json.dumps(d))")
  done
  curl -sf --header "X-Vault-Token: $VAULT_TOKEN" \
       --request POST \
       --data "{\"data\":$data}" \
       "$VAULT_ADDR/v1/secret/data/$path" &>/dev/null
  log "  [vault]   ✓ secret/data/$path"
}

seed "clearflow/gateway"     \
     "redis_password=clearflow123" \
     "artemis_user=clearflow" \
     "artemis_password=clearflow123" \
     "jwt_secret=clearflow-dev-jwt-secret-2026"

seed "clearflow/fraud-scoring" \
     "redis_password=clearflow123"

seed "clearflow/aml-compliance" \
     "redis_password=clearflow123" \
     "mongodb_uri=mongodb://localhost:27017/clearflow_dev" \
     "mongodb_password=clearflow123"

seed "clearflow/settlement" \
     "redis_password=clearflow123" \
     "artemis_user=clearflow" \
     "artemis_password=clearflow123" \
     "datasource_password=clearflow123"

seed "clearflow/audit" \
     "redis_password=clearflow123" \
     "cassandra_password=clearflow123"

seed "clearflow/mcp-readonly-gateway" \
     "redis_password=clearflow123" \
     "elasticsearch_password=" \
     "jwt_secret=clearflow-dev-jwt-secret-2026"

log "  [vault] ✅ All secrets seeded. VAULT_ADDR=$VAULT_ADDR"
log "  [vault] Token: $VAULT_TOKEN  (dev mode — never use in production)"
