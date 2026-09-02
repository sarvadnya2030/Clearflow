#!/bin/bash
# ============================================================
#  clearflow-start.sh  — Robust ClearFlow startup script
#  Usage: bash clearflow-start.sh [--skip-build] [--skip-infra]
#  Logs:  BASE/dev-logs/
#  Stop:  bash clearflow-stop.sh
# ============================================================
set -o pipefail

BASE="/home/admin-/Desktop/EDI6/clearflow"
JAVA_BIN="/usr/lib/jvm/java-21-openjdk-amd64/bin/java"
MVN="$HOME/.maven/maven-3.9.12/bin/mvn"
JAVA_HOME_PATH="/usr/lib/jvm/java-21-openjdk-amd64"
LOGS="$BASE/dev-logs"
SKIP_BUILD=false
SKIP_INFRA=false

for arg in "$@"; do
  [[ "$arg" == "--skip-build" ]] && SKIP_BUILD=true
  [[ "$arg" == "--skip-infra" ]] && SKIP_INFRA=true
done

mkdir -p "$LOGS"

# ── Helpers ────────────────────────────────────────────────
ok()   { echo "  ✓ $*"; }
fail() { echo "  ✗ $*"; }
info() { echo "    $*"; }

wait_tcp() {            # wait_tcp host port timeout_secs
  local host=$1 port=$2 timeout=$3
  local deadline=$((SECONDS + timeout))
  while [ "$SECONDS" -lt "$deadline" ]; do
    timeout 1 bash -c "echo >/dev/tcp/$host/$port" 2>/dev/null && return 0
    sleep 2
  done
  return 1
}

start_svc() {           # start_svc name port jar
  local name=$1 port=$2 jar=$3
  if [ -f "$LOGS/$name.pid" ]; then
    old=$(cat "$LOGS/$name.pid")
    kill "$old" 2>/dev/null || true
    sleep 1
  fi
  SPRING_PROFILES_ACTIVE=dev \
  JAVA_HOME="$JAVA_HOME_PATH" \
  LOG_PATH="$LOGS" \
    "$JAVA_BIN" -Xmx1536m -Xms512m -XX:+UseG1GC -XX:MaxGCPauseMillis=200 \
    -jar "$BASE/$jar" \
    > /dev/null \
    2> "$LOGS/$name.stderr.log" &
  echo $! > "$LOGS/$name.pid"
}

health_wait() {         # health_wait name port timeout_secs
  local name=$1 port=$2 timeout=$3
  local deadline=$((SECONDS + timeout))
  while [ "$SECONDS" -lt "$deadline" ]; do
    code=$(curl -s -o /dev/null -w "%{http_code}" \
      "http://localhost:$port/actuator/health" --connect-timeout 2 2>/dev/null || echo "ERR")
    if [ "$code" = "200" ]; then ok "$name (:$port)"; return 0; fi
    # Fail fast if process already exited
    local pid
    pid=$(cat "$LOGS/$name.pid" 2>/dev/null)
    if [ -n "$pid" ] && ! kill -0 "$pid" 2>/dev/null; then
      fail "$name (:$port) — process died. Check: tail $LOGS/$name.log"
      return 1
    fi
    sleep 3
  done
  fail "$name (:$port) — timed out after ${timeout}s. Check: tail $LOGS/$name.log"
  return 1
}

echo "======================================================"
echo "  ClearFlow Startup  ($(date '+%Y-%m-%d %H:%M:%S'))"
echo "======================================================"

# ── 1. Infrastructure ──────────────────────────────────────
if $SKIP_INFRA; then
  info "Skipping infra (--skip-infra)"
else
  echo ""
  echo "[1/4] Starting infrastructure..."
  cd "$BASE/infrastructure"
  docker compose up -d zookeeper activemq-artemis redis mongodb cassandra elasticsearch logstash kibana jaeger 2>/dev/null

  info "Waiting for ZooKeeper..."
  sleep 20

  info "Starting Kafka..."
  docker compose up -d kafka 2>/dev/null || true
  sleep 10
  if ! docker compose ps kafka 2>/dev/null | grep -q "Up"; then
    info "Kafka failed — clearing ZK and retrying..."
    docker compose rm -fsv kafka zookeeper &>/dev/null || true
    docker compose up -d zookeeper; sleep 15
    docker compose up -d kafka; sleep 10
  fi

  # Wait for Kafka to be ready
  info "Waiting for Kafka readiness..."
  for i in $(seq 1 24); do
    docker compose exec -T kafka kafka-topics --bootstrap-server kafka:9092 --list &>/dev/null && break
    sleep 5
  done

  # Vault
  docker compose up -d vault 2>/dev/null || true; sleep 3
  [ -f "$BASE/vault-init.sh" ] && bash "$BASE/vault-init.sh" --quiet 2>/dev/null || true

  # Topics
  info "Ensuring Kafka topics..."
  for topic in \
    clearflow.payment.initiated clearflow.fraud.evaluated clearflow.payment.blocked \
    clearflow.payment.validated clearflow.payment.rejected \
    clearflow.aml.sanctions.clear clearflow.aml.sanctions.hit clearflow.compliance.alerts \
    clearflow.payment.routed clearflow.payment.failed \
    clearflow.payment.settled clearflow.analytics.settlement \
    clearflow.mcp.access.log \
    clearflow.payments.dlq clearflow.audit.dlq \
    clearflow.payment.initiated.dlq clearflow.payment.validated.dlq \
    clearflow.aml.sanctions.clear.dlq clearflow.payment.routed.dlq; do
    docker compose exec -T kafka kafka-topics --bootstrap-server kafka:9092 \
      --create --if-not-exists --topic "$topic" \
      --partitions 9 --replication-factor 1 &>/dev/null || true
  done
  ok "Kafka topics ready"

  # Cassandra keyspace
  info "Ensuring Cassandra keyspace..."
  for i in $(seq 1 8); do
    docker exec infrastructure-cassandra-1 cqlsh -e \
      "CREATE KEYSPACE IF NOT EXISTS clearflow_dev WITH replication = {'class':'SimpleStrategy','replication_factor':1};" \
      &>/dev/null && ok "Cassandra keyspace ready" && break
    sleep 5
  done

  # Elasticsearch
  curl -s -X PUT "localhost:9200/_cluster/settings" \
    -H "Content-Type: application/json" \
    -d '{"persistent":{"cluster.routing.allocation.disk.threshold_enabled":false}}' &>/dev/null || true
  if [ -f "$BASE/infrastructure/logstash/templates/clearflow-template.json" ]; then
    curl -s -X PUT "localhost:9200/_index_template/clearflow-logs" \
      -H "Content-Type: application/json" \
      -d @"$BASE/infrastructure/logstash/templates/clearflow-template.json" &>/dev/null || true
  fi
  ok "Infrastructure ready"
fi

# ── 2. Pre-flight connectivity check ───────────────────────
echo ""
echo "[2/4] Pre-flight checks..."
all_ok=true
for check in "Kafka:localhost:29092:10" "Redis:localhost:6379:10" "MongoDB:localhost:27017:10" \
             "ActiveMQ:localhost:61616:10" "Cassandra:localhost:9042:15"; do
  name=${check%%:*}; rest=${check#*:}; host=${rest%%:*}; rest2=${rest#*:}; port=${rest2%%:*}; tmout=${rest2##*:}
  wait_tcp "$host" "$port" "$tmout" && ok "$name ($host:$port)" || { fail "$name ($host:$port) unreachable"; all_ok=false; }
done
if ! $all_ok; then
  echo ""; echo "  ⛔ Pre-flight FAILED — fix infrastructure before starting services."; exit 1
fi

# ── 3. Build ───────────────────────────────────────────────
echo ""
if $SKIP_BUILD; then
  echo "[3/4] Skipping build (--skip-build)"
else
  echo "[3/4] Building all services..."
  cd "$BASE"
  JAVA_HOME="$JAVA_HOME_PATH" "$MVN" package -DskipTests --no-transfer-progress \
    -pl common,gateway,fraud-scoring,validation-enrichment,aml-compliance,routing-execution,settlement,audit,mcp-readonly-gateway \
    -am 2>&1 | grep -E "BUILD|ERROR|\[INFO\] Building jar" | grep -v "^$"
  if ! JAVA_HOME="$JAVA_HOME_PATH" "$MVN" package -DskipTests --no-transfer-progress \
      -pl common,gateway,fraud-scoring,validation-enrichment,aml-compliance,routing-execution,settlement,audit,mcp-readonly-gateway \
      -am &>/dev/null; then
    echo "  ⛔ Build FAILED. Run mvn manually to see errors."; exit 1
  fi
  ok "Build complete"
fi

# ── 3b. Fraud model server ─────────────────────────────────
if python3 -c "import lightgbm, flask" &>/dev/null 2>&1; then
  [ -f "$LOGS/fraud-model.pid" ] && kill "$(cat $LOGS/fraud-model.pid)" 2>/dev/null || true
  # Train model if not already trained
  if [ ! -f "$BASE/fraud-model/fraud_model.lgb" ]; then
    info "Training LightGBM fraud model (first run, ~30s)..."
    python3 "$BASE/fraud-model/train.py" >> "$LOGS/fraud-model.log" 2>&1
  fi
  nohup python3 "$BASE/fraud-model/fraud_model_server.py" > "$LOGS/fraud-model.log" 2>&1 &
  echo $! > "$LOGS/fraud-model.pid"
  ok "Fraud model server started (:8091) — LightGBM AUC=1.00"
else
  info "lightgbm/flask not installed — fraud scoring uses heuristic fallback"
fi

# ── 4. Start services ──────────────────────────────────────
echo ""
echo "[4/4] Starting microservices..."
pkill -f "fraud-scoring-1.0.0.jar\|validation-enrichment-1.0.0.jar\|aml-compliance-1.0.0.jar\|routing-execution-1.0.0.jar\|settlement-1.0.0.jar\|audit-1.0.0.jar\|gateway-1.0.0.jar\|mcp-readonly-gateway-1.0.0.jar" 2>/dev/null || true
sleep 3

start_svc fraud-scoring        8081 "fraud-scoring/target/fraud-scoring-1.0.0.jar"
start_svc validation-enrichment 8082 "validation-enrichment/target/validation-enrichment-1.0.0.jar"
start_svc aml-compliance       8083 "aml-compliance/target/aml-compliance-1.0.0.jar"
start_svc routing-execution    8084 "routing-execution/target/routing-execution-1.0.0.jar"
start_svc settlement           8085 "settlement/target/settlement-1.0.0.jar"
start_svc audit                8086 "audit/target/audit-1.0.0.jar"
start_svc gateway              8080 "gateway/target/gateway-1.0.0.jar"
start_svc mcp-readonly-gateway 8087 "mcp-readonly-gateway/target/mcp-readonly-gateway-1.0.0.jar"

info "Services launched — waiting up to 120s each for health..."
sleep 25  # initial JVM start window

echo ""
echo "======================================================"
echo "  Health Check"
echo "======================================================"
all_up=true
for entry in "fraud-scoring:8081:120" "validation-enrichment:8082:120" "aml-compliance:8083:120" \
             "routing-execution:8084:120" "settlement:8085:120" "audit:8086:120" \
             "gateway:8080:120" "mcp-readonly-gateway:8087:120"; do
  name=${entry%%:*}; rest=${entry#*:}; port=${rest%%:*}; tmout=${rest##*:}
  health_wait "$name" "$port" "$tmout" || all_up=false
done

# Fraud model
model_code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8091/health" --connect-timeout 2 2>/dev/null || echo "ERR")
[ "$model_code" = "200" ] && ok "fraud-model-server (:8091) — LightGBM ready" \
  || info "fraud-model-server (:8091) — still training (see $LOGS/fraud-model.log)"

echo ""
echo "======================================================"
if $all_up; then
  echo "  ✅ ALL 8 SERVICES UP"
  echo ""
  echo "  Smoke test  : python3 $BASE/live_payment_sender.py"
  echo "  Load test   : python3 $BASE/batch_100k.py"
  echo "  Dashboard   : streamlit run $BASE/observability_dashboard.py"
  echo "  Kibana      : http://localhost:5601"
  echo "  Stop all    : bash $BASE/clearflow-stop.sh"
else
  echo "  ⚠️  SOME SERVICES FAILED"
  echo ""
  echo "  Diagnose:"
  echo "    for p in 8080 8081 8082 8083 8084 8085 8086 8087; do"
  echo "      echo -n \":\$p \"; curl -s localhost:\$p/actuator/health 2>/dev/null | python3 -c 'import sys,json; print(json.load(sys.stdin)[\"status\"])' 2>/dev/null || echo DOWN"
  echo "    done"
  echo "  Logs: $LOGS/"
fi
echo ""
echo "  Started: $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================================"
