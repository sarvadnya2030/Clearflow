#!/bin/bash
# ClearFlow Live Traffic Startup Script — mTLS Edition
# Starts minimal infrastructure + all 8 microservices with dev,ssl profiles
# Certificates are auto-generated if certs/ does not exist.

set -o pipefail   # fail on pipe errors but not unset-var errors
# (no set -e: we use explicit || true / error checks to avoid false aborts)

BASE="/home/admin-/Desktop/EDI6/clearflow"
JAVA_BIN="/usr/lib/jvm/java-21-openjdk-amd64/bin/java"
MVN="$HOME/.maven/maven-3.9.12/bin/mvn"
JAVA_HOME_PATH="/usr/lib/jvm/java-21-openjdk-amd64"
LOGS="$BASE/dev-logs"
export CLEARFLOW_CERTS_DIR="$BASE/certs"

mkdir -p "$LOGS"

echo "======================================================"
echo "  ClearFlow Live Traffic — mTLS ENABLED"
echo "======================================================"
echo ""

# ── 0. Certificate generation ──────────────────────────────
echo "[0/4] Checking mTLS certificates..."
if [ ! -d "$BASE/certs" ] || [ ! -f "$BASE/certs/clearflow-ca.p12" ]; then
  echo "      certs/ directory not found or incomplete — generating now..."
  bash "$BASE/generate-mtls-certs.sh"
else
  echo "      Certificates already present in $BASE/certs — skipping generation."
  echo "      (Delete certs/ and rerun to regenerate.)"
fi

# ── 1. Infrastructure ──────────────────────────────────────
echo ""
echo "[1/4] Starting infrastructure..."
cd "$BASE/infrastructure"

docker compose up -d zookeeper activemq-artemis redis mongodb cassandra elasticsearch logstash kibana

echo "      Waiting 25s for ZooKeeper to stabilise..."
sleep 25

# Kafka: start separately — if it crashes with NodeExistsException, restart zookeeper first
echo "      Starting Kafka..."
docker compose up -d kafka 2>/dev/null || true
sleep 10
# If Kafka exited due to stale ZK node, bounce zookeeper volume and retry once
if ! docker compose ps kafka 2>/dev/null | grep -q "Up"; then
  echo "      Kafka failed to start (stale ZK node) — clearing ZooKeeper and retrying..."
  docker compose rm -fsv kafka zookeeper &>/dev/null || true
  docker compose up -d zookeeper
  sleep 15
  docker compose up -d kafka
  sleep 10
fi

# Wait for Kafka to be truly ready
echo "      Waiting for Kafka to be ready..."
for i in $(seq 1 20); do
  if docker compose exec -T kafka kafka-topics --bootstrap-server kafka:9092 --list &>/dev/null 2>&1; then
    echo "      Kafka ready."
    break
  fi
  echo "      Kafka not ready yet ($i/20), retrying in 5s..."
  sleep 5
done

# ── Vault (start first so secrets are ready before services) ─────────────────
echo "      Starting Vault (dev mode)..."
docker compose up -d vault 2>/dev/null || true
sleep 5
# Seed secrets if vault-init.sh exists
if [ -f "$BASE/vault-init.sh" ]; then
  bash "$BASE/vault-init.sh" --quiet || echo "      ⚠️  Vault seed failed (non-fatal — using application.yml defaults)"
fi

echo "      Creating Kafka topics..."
for topic in \
  clearflow.payment.initiated \
  clearflow.fraud.evaluated clearflow.payment.blocked \
  clearflow.payment.validated clearflow.payment.rejected \
  clearflow.aml.sanctions.clear clearflow.aml.sanctions.hit clearflow.compliance.alerts \
  clearflow.payment.routed clearflow.payment.failed \
  clearflow.payment.settled clearflow.analytics.settlement \
  clearflow.mcp.access.log \
  clearflow.payments.dlq clearflow.audit.dlq \
  clearflow.payment.initiated.dlq clearflow.payment.validated.dlq \
  clearflow.aml.sanctions.clear.dlq clearflow.payment.routed.dlq; do
  docker compose exec -T kafka kafka-topics \
    --bootstrap-server kafka:9092 \
    --create --if-not-exists \
    --topic "$topic" \
    --partitions 9 --replication-factor 1 \
    &>/dev/null && echo "      topic $topic OK" || true
done

# Ensure existing topics have 9 partitions (alter is a no-op if already >= 9)
for topic in \
  clearflow.payment.initiated clearflow.fraud.evaluated clearflow.payment.blocked \
  clearflow.payment.validated clearflow.payment.rejected \
  clearflow.aml.sanctions.clear clearflow.aml.sanctions.hit \
  clearflow.payment.routed clearflow.payment.settled; do
  docker compose exec -T kafka kafka-topics \
    --bootstrap-server kafka:9092 --alter \
    --topic "$topic" --partitions 9 &>/dev/null || true
done

# Create Cassandra keyspace for audit service
echo "      Creating Cassandra keyspace clearflow_dev..."
for i in $(seq 1 6); do
  if docker exec infrastructure-cassandra-1 cqlsh -e \
    "CREATE KEYSPACE IF NOT EXISTS clearflow_dev WITH replication = {'class':'SimpleStrategy','replication_factor':1};" \
    &>/dev/null 2>&1; then
    echo "      Cassandra keyspace ready."
    break
  fi
  echo "      Cassandra not ready yet ($i/6), retrying in 5s..."
  sleep 5
done

# Configure Elasticsearch
echo "      Configuring Elasticsearch..."
curl -s -X PUT "localhost:9200/_cluster/settings" \
  -H "Content-Type: application/json" \
  -d '{"persistent":{"cluster.routing.allocation.disk.threshold_enabled":false}}' \
  &>/dev/null || true

# Apply Elasticsearch index template for structured log ingestion
echo "      Applying Elasticsearch index template..."
if [ -f "$BASE/infrastructure/logstash/templates/clearflow-template.json" ]; then
  curl -s -X PUT "localhost:9200/_index_template/clearflow-logs" \
    -H "Content-Type: application/json" \
    -d @"$BASE/infrastructure/logstash/templates/clearflow-template.json" \
    &>/dev/null && echo "      ES template applied." || echo "      ES template skipped (ES may not be ready)"
fi

# ── 2. Build ───────────────────────────────────────────────
echo ""
echo "[2/4] Building all services (skipping tests)..."
cd "$BASE"

JAVA_HOME="$JAVA_HOME_PATH" "$MVN" package -DskipTests --no-transfer-progress \
  -pl common,gateway,fraud-scoring,validation-enrichment,aml-compliance,routing-execution,settlement,audit,mcp-readonly-gateway \
  -am 2>&1 | grep -E "BUILD|ERROR|WARNING|\\[INFO\\] Building" | grep -v "^$"

echo "      Build complete."

# ── 3. Start services ──────────────────────────────────────
echo ""
echo "[3/4] Starting microservices with TLS (profiles: dev,ssl)..."

start_service() {
  local name=$1
  local port=$2
  local jar=$3

  if [ -f "$LOGS/$name.pid" ]; then
    old_pid=$(cat "$LOGS/$name.pid")
    kill "$old_pid" 2>/dev/null || true
  fi

  echo "      Starting $name on :$port (HTTPS)..."
  # stdout → /dev/null: the ROLLING_FILE appender owns the log file (no duplicates)
  # stderr → .stderr.log: captures JVM startup noise and Logback internal messages
  SPRING_PROFILES_ACTIVE=dev,ssl \
  CLEARFLOW_CERTS_DIR="$CLEARFLOW_CERTS_DIR" \
  JAVA_HOME="$JAVA_HOME_PATH" \
  LOG_PATH="$LOGS" \
    "$JAVA_BIN" \
    -Xmx1536m -Xms512m \
    -XX:+UseG1GC -XX:MaxGCPauseMillis=200 \
    -jar "$BASE/$jar" \
    > /dev/null \
    2> "$LOGS/$name.stderr.log" &
  echo $! > "$LOGS/$name.pid"
}

start_service fraud-scoring       8081 "fraud-scoring/target/fraud-scoring-1.0.0.jar"
sleep 3
start_service validation-enrichment 8082 "validation-enrichment/target/validation-enrichment-1.0.0.jar"
sleep 3
start_service aml-compliance      8083 "aml-compliance/target/aml-compliance-1.0.0.jar"
sleep 3
start_service routing-execution   8084 "routing-execution/target/routing-execution-1.0.0.jar"
sleep 3
start_service settlement          8085 "settlement/target/settlement-1.0.0.jar"
sleep 3
start_service audit               8086 "audit/target/audit-1.0.0.jar"
sleep 3
start_service gateway             8080 "gateway/target/gateway-1.0.0.jar"
sleep 3
start_service mcp-readonly-gateway 8087 "mcp-readonly-gateway/target/mcp-readonly-gateway-1.0.0.jar"

# ── 4. Health check (polls each service over HTTPS, up to 90s per service) ────
echo ""
echo "[4/4] Waiting for services to become healthy over HTTPS (max 90s each)..."

wait_for_service() {
  local name=$1
  local port=$2
  local deadline=$((SECONDS + 90))
  local last_code=""
  while [ "$SECONDS" -lt "$deadline" ]; do
    last_code=$(curl -s -o /dev/null -w "%{http_code}" --insecure \
      "https://localhost:$port/actuator/health" --connect-timeout 2 2>/dev/null || echo "ERR")
    if [ "$last_code" = "200" ]; then
      echo "  ✓ $name (:$port) [HTTPS]"
      return 0
    fi
    sleep 3
  done
  echo "  ✗ $name (:$port) → HTTP $last_code after 90s"
  echo "    → tail $LOGS/$name.log  OR  cat $LOGS/$name.stderr.log"
  return 1
}

# Give all services an initial 20s head-start (JVM startup + Spring context)
echo "      (Initial 20s JVM start window...)"
sleep 20

echo ""
echo "======================================================"
echo "  Health Check (mTLS)"
echo "======================================================"
all_up=true
for entry in "fraud-scoring:8081" "validation-enrichment:8082" "aml-compliance:8083" \
             "routing-execution:8084" "settlement:8085" "audit:8086" \
             "gateway:8080" "mcp-readonly-gateway:8087"; do
  name=${entry%%:*}
  port=${entry##*:}
  wait_for_service "$name" "$port" || all_up=false
done

echo ""
if $all_up; then
  echo "  All services UP with mTLS."
  echo ""
  echo "  Quick smoke test : python3 live_payment_sender.py"
  echo "  Load test (100K) : python3 batch_100k.py"
  echo "  Dashboard        : streamlit run observability_dashboard.py"
  echo ""
  echo "  NOTE: Services are running on HTTPS. Use --insecure with curl (self-signed cert)."
  echo "  Example: curl --insecure https://localhost:8080/actuator/health"
else
  echo "  Some services failed to start."
  echo ""
  echo "  Diagnose:"
  echo "    for p in 8080 8081 8082 8083 8084 8085 8086 8087; do"
  echo "      echo -n \":\$p \"; curl --insecure -s https://localhost:\$p/actuator/health 2>/dev/null | python3 -c 'import sys,json; print(json.load(sys.stdin)[\"status\"])' 2>/dev/null || echo DOWN"
  echo "    done"
  echo ""
  echo "  Common fixes:"
  echo "    Cert missing   → bash $BASE/generate-mtls-certs.sh"
  echo "    Port clash     → pkill -f '\\.jar' && bash $BASE/start_live_traffic_tls.sh"
  echo "    Kafka lag      → check $LOGS/gateway.stderr.log for 'topic not found'"
  echo "    OOM            → reduce -Xmx below or free memory"
fi

echo ""
echo "  Certs : $CLEARFLOW_CERTS_DIR/"
echo "  Logs  : $LOGS/"
echo "  Stop  : bash $BASE/stop_live_traffic.sh"
