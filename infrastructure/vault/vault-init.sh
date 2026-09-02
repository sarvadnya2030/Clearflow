#!/usr/bin/env sh
set -e

export VAULT_ADDR=${VAULT_ADDR:-http://vault:8200}
export VAULT_TOKEN=${VAULT_TOKEN:-clearflow-dev-token}

vault secrets enable -path=secret kv-v2 || true
vault policy write clearflow /vault/policies/clearflow-policy.hcl || true
vault kv put secret/clearflow/db oracle_password=${ORACLE_PASSWORD:-clearflow123} redis_password=${REDIS_PASSWORD:-clearflow123}
vault kv put secret/clearflow/messaging artemis_password=${ARTEMIS_PASSWORD:-clearflow123}

echo "Vault initialization complete"
