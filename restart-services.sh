#!/usr/bin/env bash
# Restart all ClearFlow microservices (native JARs)
set -e
ROOT="/home/admin-/Desktop/EDI6/clearflow"
LOGDIR="$ROOT/dev-logs"
JAVA="java"

start_svc() {
  local name="$1"
  local jar="$2"
  local port="$3"
  local extra="${4:-}"
  echo "Starting $name on :$port..."
  nohup $JAVA \
    -Dspring.profiles.active=dev \
    -Dserver.port="$port" \
    $extra \
    -jar "$jar" \
    > "$LOGDIR/$name.log" 2>&1 &
  echo $! > "$LOGDIR/$name.pid"
  echo "  PID=$(cat $LOGDIR/$name.pid)"
}

mkdir -p "$LOGDIR"

# Kill any lingering processes
for pid_file in "$LOGDIR"/*.pid; do
  pid=$(cat "$pid_file" 2>/dev/null || true)
  [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
done
sleep 2

start_svc "gateway"                "$ROOT/gateway/target/gateway-1.0.0.jar"                          8080
sleep 3
start_svc "fraud-scoring"          "$ROOT/fraud-scoring/target/fraud-scoring-1.0.0.jar"              8081
start_svc "validation-enrichment"  "$ROOT/validation-enrichment/target/validation-enrichment-1.0.0.jar" 8082
start_svc "aml-compliance"         "$ROOT/aml-compliance/target/aml-compliance-1.0.0.jar"            8083
start_svc "routing-execution"      "$ROOT/routing-execution/target/routing-execution-1.0.0.jar"      8084
start_svc "settlement"             "$ROOT/settlement/target/settlement-1.0.0.jar"                    8085
start_svc "audit"                  "$ROOT/audit/target/audit-1.0.0.jar"                              8086
start_svc "mcp-readonly-gateway"   "$ROOT/mcp-readonly-gateway/target/mcp-readonly-gateway-1.0.0.jar" 8087

echo ""
echo "All services launched. Waiting 20s for startup..."
sleep 20
echo "Health checks:"
for port_name in "8080 gateway" "8081 fraud-scoring" "8082 validation-enrichment" "8083 aml-compliance" "8084 routing-execution" "8085 settlement" "8086 audit" "8087 mcp-readonly-gateway"; do
  p=$(echo $port_name | awk '{print $1}')
  n=$(echo $port_name | awk '{print $2}')
  status=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$p/actuator/health" 2>/dev/null || echo "ERR")
  echo "  :$p $n → $status"
done
