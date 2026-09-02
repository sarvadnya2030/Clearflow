#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  ClearFlow  —  DEMO START SCRIPT
#  Run:  bash START_DEMO.sh
#  Brings up all 8 services + frontend, verifies everything green.
# ═══════════════════════════════════════════════════════════════

set -o pipefail

BASE="/home/admin-/Desktop/EDI6/clearflow"
JAVA="/usr/lib/jvm/java-21-openjdk-amd64/bin/java"
JAVA_HOME_PATH="/usr/lib/jvm/java-21-openjdk-amd64"
LOGS="$BASE/dev-logs"
FRONT="$BASE/frontend"
[ -f "$BASE/.env.local" ] && source "$BASE/.env.local"
TOKEN="eyJhbGciOiAiSFMyNTYiLCAidHlwIjogIkpXVCJ9.eyJzdWIiOiAiZGVtby1vcHMiLCAiaXNzIjogImNsZWFyZmxvdy1kZXYiLCAiaWF0IjogMTc3ODg2MTYxMSwgImV4cCI6IDE4OTM0NTYwMDAsICJzY29wZSI6ICJtY3A6cmVhZCBtY3A6YWRtaW4ifQ._Iz89MiCOyVY9m0MUsuSJhlFqsXY-OYvlV2ML2SFPuQ"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

mkdir -p "$LOGS"

banner() {
  echo ""
  echo -e "${BOLD}${BLUE}══════════════════════════════════════════════════${NC}"
  echo -e "${BOLD}${BLUE}  ClearFlow — AI-Augmented Payment Processing Demo ${NC}"
  echo -e "${BOLD}${BLUE}══════════════════════════════════════════════════${NC}"
  echo ""
}

ok()   { echo -e "  ${GREEN}✓${NC}  $1"; }
warn() { echo -e "  ${YELLOW}⚠${NC}  $1"; }
fail() { echo -e "  ${RED}✗${NC}  $1"; }
step() { echo -e "\n${BOLD}[$1]${NC} $2"; }

# ── Check if a port is already serving ────────────────────────
port_up() {
  curl -s --max-time 2 "http://localhost:$1/actuator/health" 2>/dev/null \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null \
    | grep -q "UP"
}

# ── Start a JAR service (skip if already UP) ──────────────────
start_svc() {
  local name=$1 port=$2 jar=$3
  shift 3
  local extra_args="$@"

  if port_up $port; then
    ok "$name :$port already UP — skipping"
    return
  fi

  # Kill stale PID if exists
  if [ -f "$LOGS/$name.pid" ]; then
    kill "$(cat $LOGS/$name.pid)" 2>/dev/null || true
    rm -f "$LOGS/$name.pid"
  fi

  echo -e "      Starting ${BOLD}$name${NC} on :$port ..."
  SPRING_PROFILES_ACTIVE=dev \
  JAVA_HOME="$JAVA_HOME_PATH" \
  LOG_PATH="$LOGS" \
    "$JAVA" \
    -Xmx1536m -Xms512m \
    -XX:+UseG1GC -XX:MaxGCPauseMillis=200 \
    -jar "$BASE/$jar" \
    $extra_args \
    > /dev/null \
    2> "$LOGS/$name.stderr.log" &
  echo $! > "$LOGS/$name.pid"
}

# ── Wait for a port with timeout ──────────────────────────────
wait_for() {
  local name=$1 port=$2 timeout=${3:-60}
  local elapsed=0
  printf "      Waiting for %s :%-4s  " "$name" "$port"
  while ! port_up $port; do
    sleep 3; elapsed=$((elapsed+3))
    printf "."
    if [ $elapsed -ge $timeout ]; then
      echo ""
      fail "$name :$port did not come up in ${timeout}s"
      echo "         Check: tail -50 $LOGS/$name.stderr.log"
      return 1
    fi
  done
  echo ""
  ok "$name :$port UP"
}

# ═══════════════════════════════════════════════════════════════
banner

# ── STEP 1: Infrastructure ─────────────────────────────────────
step "1/5" "Infrastructure (Docker)"

cd "$BASE/infrastructure"

INFRA_UP=$(docker ps --format "{{.Names}}" 2>/dev/null | grep -c "infrastructure" || echo 0)
if [ "$INFRA_UP" -ge 5 ]; then
  ok "Infrastructure containers already running ($INFRA_UP containers)"
else
  warn "Starting infrastructure containers..."
  docker compose up -d zookeeper activemq-artemis redis mongodb cassandra elasticsearch 2>/dev/null
  echo "      Waiting 20s for ZooKeeper..."
  sleep 20

  docker compose up -d kafka 2>/dev/null || true
  sleep 8

  # Kafka retry if failed
  if ! docker compose ps kafka 2>/dev/null | grep -q "Up"; then
    warn "Kafka failed — clearing stale ZK node and retrying..."
    docker compose rm -fsv kafka zookeeper &>/dev/null || true
    docker compose up -d zookeeper && sleep 15
    docker compose up -d kafka && sleep 10
  fi

  # Wait for Kafka to be ready
  printf "      Waiting for Kafka broker  "
  for i in $(seq 1 24); do
    if docker compose exec -T kafka kafka-topics --bootstrap-server kafka:9092 --list &>/dev/null 2>&1; then
      echo ""; ok "Kafka ready"; break
    fi
    printf "."; sleep 5
    if [ $i -eq 24 ]; then echo ""; fail "Kafka not ready after 2 min — check docker logs"; fi
  done

  # Ensure required Kafka topics exist
  for topic in payment.initiated payment.fraud.scored payment.validated payment.aml.checked \
               payment.routed payment.settled payment.failed payment.audit.logged \
               payment.dlq clearflow.mcp.access; do
    docker compose exec -T kafka kafka-topics \
      --bootstrap-server kafka:9092 --create --if-not-exists \
      --topic "$topic" --partitions 12 --replication-factor 1 &>/dev/null || true
  done
  ok "Kafka topics verified"
fi

# ── STEP 2: Core Services ──────────────────────────────────────
step "2/5" "Starting microservices (ports 8080–8086)"

start_svc fraud-scoring          8081 "fraud-scoring/target/fraud-scoring-1.0.0.jar"
start_svc validation-enrichment  8082 "validation-enrichment/target/validation-enrichment-1.0.0.jar"
start_svc aml-compliance         8083 "aml-compliance/target/aml-compliance-1.0.0.jar"
start_svc routing-execution      8084 "routing-execution/target/routing-execution-1.0.0.jar"
start_svc settlement             8085 "settlement/target/settlement-1.0.0.jar"
start_svc audit                  8086 "audit/target/audit-1.0.0.jar"
start_svc gateway                8080 "gateway/target/gateway-1.0.0.jar" \
  "--spring.cloud.vault.enabled=false"

# ── STEP 3: MCP Gateway ────────────────────────────────────────
step "3/5" "MCP AI Gateway :8087  (NVIDIA Nemotron 30B)"

start_svc mcp-readonly-gateway 8087 \
  "mcp-readonly-gateway/target/mcp-readonly-gateway-1.0.0.jar" \
  "--spring.cloud.vault.enabled=false"

# ── STEP 4: Wait for all services ─────────────────────────────
step "4/5" "Waiting for all services to be healthy"

wait_for gateway                8080 90
wait_for fraud-scoring          8081 90
wait_for validation-enrichment  8082 90
wait_for aml-compliance         8083 90
wait_for routing-execution      8084 90
wait_for settlement             8085 90
wait_for audit                  8086 90
wait_for mcp-readonly-gateway   8087 90

# ── STEP 5: Frontend ───────────────────────────────────────────
step "5/5" "Frontend (React/Vite on :3001)"

if curl -so /dev/null -w "%{http_code}" http://localhost:3001/ 2>/dev/null | grep -q "200"; then
  ok "Frontend already running at http://localhost:3001"
else
  warn "Starting Vite dev server..."
  cd "$FRONT"
  nohup npm run dev > "$LOGS/frontend.log" 2>&1 &
  echo $! > "$LOGS/frontend.pid"
  printf "      Waiting for frontend  "
  for i in $(seq 1 20); do
    sleep 3; printf "."
    if curl -so /dev/null -w "%{http_code}" http://localhost:3001/ 2>/dev/null | grep -q "200"; then
      echo ""; ok "Frontend UP at http://localhost:3001"; break
    fi
    if [ $i -eq 20 ]; then echo ""; fail "Frontend did not start — check $LOGS/frontend.log"; fi
  done
fi

# ── FINAL HEALTH CHECK ─────────────────────────────────────────
echo ""
echo -e "${BOLD}${BLUE}══════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  FINAL STATUS${NC}"
echo -e "${BOLD}${BLUE}══════════════════════════════════════════════════${NC}"

ALL_UP=true

# Use MCP aggregated health check
sleep 3
HEALTH=$(curl -s --max-time 5 "http://localhost:8087/mcp/diagnostics/health-summary" \
  -H "Authorization: Bearer $TOKEN" 2>/dev/null)

if [ -n "$HEALTH" ]; then
  echo "$HEALTH" | python3 -c "
import sys, json
d = json.load(sys.stdin)
green = '\033[0;32m'; red = '\033[0;31m'; nc = '\033[0m'; bold = '\033[1m'
all_up = True
for name, status in sorted(d.items()):
    if status == 'UP':
        print(f'  {green}✓{nc}  {bold}{name}{nc}  → UP')
    else:
        print(f'  {red}✗{nc}  {bold}{name}{nc}  → {status}')
        all_up = False
if all_up:
    print(f'\n  {green}{bold}ALL 8 MICROSERVICES OPERATIONAL{nc}')
else:
    print(f'\n  {red}{bold}SOME SERVICES DOWN — check dev-logs/{nc}')
"
else
  warn "MCP health-summary not reachable — checking directly..."
  for p in 8080 8081 8082 8083 8084 8085 8086 8087; do
    if port_up $p; then ok ":$p UP"
    else fail ":$p DOWN"; ALL_UP=false; fi
  done
fi

echo ""
if curl -so /dev/null -w "%{http_code}" http://localhost:3001/ 2>/dev/null | grep -q "200"; then
  ok "Frontend → http://localhost:3001"
else
  fail "Frontend not responding"
  ALL_UP=false
fi

echo ""
echo -e "${BOLD}${BLUE}══════════════════════════════════════════════════${NC}"
if $ALL_UP; then
  echo -e "  ${GREEN}${BOLD}DEMO READY  →  http://localhost:3001${NC}"
else
  echo -e "  ${YELLOW}${BOLD}DEMO PARTIALLY READY — fix issues above${NC}"
fi
echo -e "${BOLD}${BLUE}══════════════════════════════════════════════════${NC}"
echo ""
echo "  Useful commands:"
echo "    Tail MCP log:      tail -f $LOGS/mcp-readonly-gateway.stderr.log"
echo "    Tail gateway log:  tail -f $LOGS/gateway.log"
echo "    Stop everything:   bash $BASE/stop_live_traffic.sh"
echo ""
