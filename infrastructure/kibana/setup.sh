#!/usr/bin/env bash
# Kibana auto-setup for ClearFlow ELK observability
# ────────────────────────────────────────────────────────────────────────────────
# Imports saved objects (index patterns, dashboards) via Kibana API.
# Run after docker-compose up when Kibana is healthy.
#
# Usage:
#   ./setup.sh
#   KIBANA_URL=http://kibana:5601 ./setup.sh
# ────────────────────────────────────────────────────────────────────────────────

set -euo pipefail

KIBANA_URL="${KIBANA_URL:-http://localhost:5601}"
ES_URL="${ES_URL:-http://localhost:9200}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

GREEN="\033[32m"
YELLOW="\033[33m"
CYAN="\033[36m"
RESET="\033[0m"

info()    { printf "${CYAN}[kibana-setup]${RESET} $1\n"; }
ok()      { printf "${GREEN}[kibana-setup] ✓ $1${RESET}\n"; }
warning() { printf "${YELLOW}[kibana-setup] ⚠ $1${RESET}\n"; }

# ── Wait for Kibana ───────────────────────────────────────────────────────────

wait_for_kibana() {
  info "Waiting for Kibana at $KIBANA_URL ..."
  local attempts=0
  until curl -s "$KIBANA_URL/api/status" | grep -q '"level":"available"' 2>/dev/null; do
    attempts=$((attempts + 1))
    if [ $attempts -ge 30 ]; then
      echo "Kibana not ready after 150s — aborting setup"
      exit 1
    fi
    sleep 5
  done
  ok "Kibana is ready"
}

# ── Create index patterns ─────────────────────────────────────────────────────

create_index_pattern() {
  local title="$1"
  local time_field="${2:-@timestamp}"
  info "Creating index pattern: $title"

  local payload
  payload=$(printf '{"attributes":{"title":"%s","timeFieldName":"%s"}}' "$title" "$time_field")

  local status
  status=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "$KIBANA_URL/api/saved_objects/index-pattern" \
    -H "kbn-xsrf: true" \
    -H "Content-Type: application/json" \
    -d "$payload")

  if [ "$status" -eq 200 ] || [ "$status" -eq 409 ]; then
    ok "Index pattern '$title' ready (status=$status)"
  else
    warning "Index pattern '$title' returned status $status"
  fi
}

# ── Import saved objects (dashboards, visualizations) ─────────────────────────

import_saved_objects() {
  local ndjson_file="$SCRIPT_DIR/export.ndjson"
  if [ ! -f "$ndjson_file" ]; then
    warning "export.ndjson not found — skipping dashboard import"
    return
  fi

  info "Importing saved objects from export.ndjson ..."
  local status
  status=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "$KIBANA_URL/api/saved_objects/_import?overwrite=true" \
    -H "kbn-xsrf: true" \
    -F "file=@$ndjson_file")

  if [ "$status" -eq 200 ] || [ "$status" -eq 201 ]; then
    ok "Saved objects imported"
  else
    warning "Import returned status $status — check export.ndjson format"
  fi
}

# ── Verify demo index in ES ────────────────────────────────────────────────────

verify_demo_data() {
  info "Checking for seeded demo data in ES ..."
  local count
  count=$(curl -s "$ES_URL/clearflow-demo/_count" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('count',0))" 2>/dev/null || echo "unknown")
  ok "clearflow-demo index has $count documents"

  info "Demo payment IDs available for /explain:"
  printf "  PAY-DEMO-AML-001      — AML sanctions hit\n"
  printf "  PAY-DEMO-FRAUD-001    — Fraud score CRITICAL\n"
  printf "  PAY-DEMO-SETTLED-001  — Full settlement (happy path)\n"
  printf "  PAY-DEMO-EMBARGO-001  — Embargo blocked\n"
  printf "  PAY-DEMO-ROUTING-001  — Rail routing failure\n"
  printf "  PAY-DEMO-STORM-001..010 — Systemic alert storm\n"
}

# ── Main ──────────────────────────────────────────────────────────────────────

main() {
  wait_for_kibana

  # Core index patterns
  create_index_pattern "clearflow-*"        "@timestamp"
  create_index_pattern "clearflow-demo"     "@timestamp"
  create_index_pattern "clearflow-gateway*" "@timestamp"
  create_index_pattern "clearflow-fraud*"   "@timestamp"
  create_index_pattern "clearflow-aml*"     "@timestamp"

  import_saved_objects
  verify_demo_data

  printf "\n${GREEN}Kibana setup complete!${RESET}\n"
  printf "Kibana:  ${CYAN}$KIBANA_URL${RESET}\n"
  printf "MCP:     ${CYAN}http://localhost:8087/mcp/payments/PAY-DEMO-AML-001/explain${RESET}\n\n"
}

main "$@"
