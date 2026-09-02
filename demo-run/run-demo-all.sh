#!/usr/bin/env bash
set -euo pipefail
ROOT="$(pwd)"
LOGDIR="$ROOT/demo-run/logs"
mkdir -p "$LOGDIR"

echo "[0] cleanup"
pkill -f 'spring-boot:run|mcp-readonly-gateway|npm run dev' 2>/dev/null || true
docker compose -f infrastructure/docker-compose.yml down --remove-orphans 2>/dev/null || true
sleep 2

echo "[1] infra"
docker compose -f infrastructure/docker-compose.yml up -d zookeeper kafka redis elasticsearch kibana
sleep 15
for i in {1..20}; do
  curl -s http://localhost:9200/_cluster/health | jq -e '.status==\"yellow\" or .status==\"green\"' >/dev/null 2>&1 && break
  echo " waiting ES..."
  sleep 3
done

echo "[2] build backend"
mvn -pl mcp-readonly-gateway -am package -DskipTests > "$LOGDIR/mcp-build.log" 2>&1
mvn -pl gateway -am package -DskipTests > "$LOGDIR/gateway-build.log" 2>&1

echo "[3] start backend"
nohup mvn -pl mcp-readonly-gateway -Dspring-boot.run.jvmArguments='-Dserver.port=8087' spring-boot:run -DskipTests > "$LOGDIR/mcp-runtime.log" 2>&1 &
sleep 3
nohup mvn -pl gateway -Dspring-boot.run.jvmArguments='-Dserver.port=8080' spring-boot:run -DskipTests > "$LOGDIR/gateway-runtime.log" 2>&1 &

echo "[4] start frontend"
cd frontend
npm ci --silent
nohup npm run dev > "$LOGDIR/frontend.log" 2>&1 &

sleep 15
echo "🚀 Demo running:"
echo " - frontend: http://localhost:3000"
echo " - gateway: http://localhost:8080"
echo " - mcp:     http://localhost:8087"
echo " - kibana:  http://localhost:5601"
echo "Ingest sample with generator + check:"
python "$ROOT/synthetic-load-generator/generate_payments.py" --count 100 --concurrency 5 --url http://localhost:8080/api/v1/payments
curl -s -H 'Authorization: Bearer demo-token' http://localhost:8087/mcp/payments/PAY-DEMO-AML-001/explain | jq .
