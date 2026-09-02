#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)/.."
DEMO_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$DEMO_DIR/logs"
mkdir -p "$LOG_DIR"

# Force cleanup of existing demo stack to avoid stale port collision.
echo "[1/6] Stopping existing compose stack and cleaning ports"
docker compose -f "$ROOT/infrastructure/docker-compose.yml" down --remove-orphans || true
pkill -f "mcp-readonly-gateway" || true

# Start full stack (with mcp gateway) and wait for health.
echo "[2/6] Starting platform stack"
docker compose -f "$ROOT/infrastructure/docker-compose.yml" up -d --build

echo "[3/6] Waiting for core services"
wait_for_url(){ local u="$1"; local t=${2:-180}; local s=0; while ! curl -s -f "$u" >/dev/null 2>&1; do sleep 5; s=$((s+5)); echo " waiting $u..."; [ "$s" -ge "$t" ] && return 1; done }
wait_for_url http://localhost:9200/_cluster/health 180
wait_for_url http://localhost:5601 180 || true
wait_for_url http://localhost:8080/actuator/health 240
wait_for_url http://localhost:8087/actuator/health 240

# Optionally start frontend in background (if not already needed)
# echo "[4/6] Starting frontend dev server"
# cd "$ROOT/frontend" && npm ci --silent && nohup npm run dev > "$LOG_DIR/frontend-dev.log" 2>&1 &

# Generate the data via synthetic load generator.
echo "[4/6] Generating payments data (2000 records)"
cd "$ROOT/synthetic-load-generator"
pip install -r requirements.txt --quiet
python generate_payments.py --count 2000 --concurrency 10 --url http://localhost:8080/api/v1/payments > "$LOG_DIR/generator.log" 2>&1

# Collect MCP logs and service logs into files.
echo "[5/6] Saving MCP + container logs"
docker compose -f "$ROOT/infrastructure/docker-compose.yml" logs mcp-readonly-gateway > "$LOG_DIR/mcp-readonly-gateway.log" 2>&1

docker compose -f "$ROOT/infrastructure/docker-compose.yml" logs gateway > "$LOG_DIR/gateway.log" 2>&1

# Run MCP check queries.
echo "[6/6] Running MCP explain/metrics checks"
PAYMENTS=(PAY-DEMO-AML-001 PAY-DEMO-FRAUD-001 PAY-DEMO-ROUTING-001 PAY-DEMO-EMBARGO-001 PAY-DEMO-SETTLED-001)
for P in "${PAYMENTS[@]}"; do
  echo "--- $P ---" >> "$LOG_DIR/mcp-checks.log"
  curl -s -H "Authorization: Bearer demo-token" "http://localhost:8087/mcp/payments/$P/explain" | jq . >> "$LOG_DIR/mcp-checks.log" 2>&1 || echo "failed for $P" >> "$LOG_DIR/mcp-checks.log"
done

curl -s -H "Authorization: Bearer demo-token" http://localhost:8087/mcp/metrics/overview | jq . >> "$LOG_DIR/mcp-checks.log" 2>&1 || true
curl -s -H "Authorization: Bearer demo-token" http://localhost:8087/mcp/metrics/rails | jq . >> "$LOG_DIR/mcp-checks.log" 2>&1 || true
curl -s -H "Authorization: Bearer demo-token" http://localhost:8087/mcp/metrics/fraud | jq . >> "$LOG_DIR/mcp-checks.log" 2>&1 || true

cat <<SUMMARY > "$LOG_DIR/demo-finished.txt"
MCP demo script completed.
Platform: gateway=8080, mcp=8087, elastic=9200, kibana=5601
Logs: $LOG_DIR
Summary: generated 2000 payments and queried MCP explain+metrics.
SUMMARY

echo "Demo finished; artifacts in $LOG_DIR"
