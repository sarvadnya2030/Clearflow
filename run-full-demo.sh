#!/usr/bin/env bash
set -euo pipefail
DEMO_STACK=1; COUNT=2000; CONCURRENCY=10
while (( $# )); do
  case "$1" in
    --use-full-stack) DEMO_STACK=0; shift ;;
    --use-demo-stack) DEMO_STACK=1; shift ;;
    --count) COUNT=${2:-$COUNT}; shift 2 ;;
    --concurrency) CONCURRENCY=${2:-$CONCURRENCY}; shift 2 ;;
    *) echo "Unknown option $1"; exit 1 ;;
  esac
done
ROOT="$(cd "$(dirname "$0")" && pwd)"
# Always start full core platform stack for a complete payment + MCP demo
COMPOSE="$ROOT/infrastructure/docker-compose.yml"
# Keep demo stack as option for minimal ELK-only experiments, but full stack is preferred
[ "$DEMO_STACK" -eq 1 ] && echo "Note: --use-demo-stack is deprecated for full demo behavior, using full stack anyway"
echo "[1/6] docker compose -f $COMPOSE up -d --build"
docker compose -f "$COMPOSE" up -d --build
wait_for_url(){ local u="$1"; local t=${2:-120}; local s=0
  while ! curl -s -f "$u" >/dev/null 2>&1; do sleep 5; s=$((s+5)); [ "$s" -ge "$t" ] && return 1; done
}
wait_for_url http://localhost:9200/_cluster/health 180
wait_for_url http://localhost:5601 180 || true
wait_for_url http://localhost:8080/actuator/health 300 || true
wait_for_url http://localhost:8087/actuator/health 300 || true
wait_for_url http://localhost:3000 120 || true
echo "[2/6] start frontend"
cd "$ROOT/frontend"; npm ci --silent
nohup npm run dev > "$ROOT/frontend/frontend-dev.log" 2>&1 &
FRONTEND_PID=$!
echo "[3/6] generator"
cd "$ROOT/synthetic-load-generator"; pip install -r requirements.txt --quiet
python generate_payments.py --count "$COUNT" --concurrency "$CONCURRENCY" --url http://localhost:8080/api/v1/payments
echo "[4/6] mcp checks"
for P in PAY-DEMO-AML-001 PAY-DEMO-FRAUD-001 PAY-DEMO-ROUTING-001 PAY-DEMO-EMBARGO-001 PAY-DEMO-SETTLED-001; do
  echo "--- $P ---"
  curl -s -H "Authorization: Bearer demo-token" "http://localhost:8087/mcp/payments/$P/explain" | jq .
done
curl -s -H "Authorization: Bearer demo-token" http://localhost:8087/mcp/metrics/overview | jq .
curl -s -H "Authorization: Bearer demo-token" http://localhost:8087/mcp/metrics/rails | jq .
curl -s -H "Authorization: Bearer demo-token" http://localhost:8087/mcp/metrics/fraud | jq .
echo "Demo done. Gateway=8080, MCP=8087, Kibana=5601, Frontend=3000"
echo "Stop with: docker compose -f $COMPOSE down; kill $FRONTEND_PID || true"
