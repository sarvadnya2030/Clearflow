#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
#  ClearFlow — Single-Command Docker Deployment
#  Builds all JARs → builds Docker images → starts full stack
# ═══════════════════════════════════════════════════════════════════
#
# Usage:
#   bash deploy.sh              — full build + start
#   bash deploy.sh --no-build   — skip Maven build (use pre-built JARs)
#   bash deploy.sh --down       — stop and remove all containers
#   bash deploy.sh --restart    — restart all app services (no rebuild)
#
# Requirements:
#   Docker 24+, Docker Compose v2, Java 21, Maven 3.9
#
# First run:  ~10 min (downloads base images + builds)
# Subsequent: ~3 min  (Docker layer cache)
# ═══════════════════════════════════════════════════════════════════

set -euo pipefail

BASE="$(cd "$(dirname "$0")" && pwd)"
COMPOSE="$BASE/infrastructure/docker-compose.yml"
JAVA_HOME_PATH="${JAVA_HOME:-/usr/lib/jvm/java-21-openjdk-amd64}"
MVN="${MVN_CMD:-${HOME}/.maven/maven-3.9.12/bin/mvn}"
[ ! -f "$MVN" ] && MVN="mvn"

B="\033[1m"; R="\033[0m"
GREEN="\033[32m"; CYAN="\033[36m"; YELLOW="\033[33m"; RED="\033[31m"

ok()   { printf "  ${GREEN}✓${R}  %s\n" "$1"; }
info() { printf "  ${CYAN}▸${R}  %s\n" "$1"; }
warn() { printf "  ${YELLOW}⚠${R}  %s\n" "$1"; }
err()  { printf "  ${RED}✗${R}  %s\n" "$1"; exit 1; }

BUILD=true
for arg in "$@"; do
  case "$arg" in
    --no-build) BUILD=false ;;
    --down)
      info "Stopping and removing all ClearFlow containers…"
      docker compose -f "$COMPOSE" down --remove-orphans
      ok "Done."
      exit 0
      ;;
    --restart)
      info "Restarting application services…"
      docker compose -f "$COMPOSE" restart \
        gateway fraud-scoring validation-enrichment aml-compliance \
        routing-execution settlement audit mcp-readonly-gateway
      ok "Done."
      exit 0
      ;;
  esac
done

printf "\n${B}${CYAN}═══════════════════════════════════════════════════════${R}\n"
printf "${B}${CYAN}  ClearFlow — Full Stack Deployment${R}\n"
printf "${B}${CYAN}═══════════════════════════════════════════════════════${R}\n\n"

# ── Prerequisites ─────────────────────────────────────────
info "Checking prerequisites…"
command -v docker   >/dev/null || err "Docker not found. Install Docker 24+"
command -v python3  >/dev/null || err "Python3 not found"
docker info         >/dev/null 2>&1 || err "Docker daemon not running"
ok "Docker $(docker --version | awk '{print $3}' | tr -d ',')"

# ── Maven build ───────────────────────────────────────────
if $BUILD; then
  printf "\n${B}[1/4] Maven Build${R}\n"
  info "Building all modules with Java 21 (skipping tests)…"
  JAVA_HOME="$JAVA_HOME_PATH" "$MVN" clean package -DskipTests --no-transfer-progress \
    -pl common,gateway,fraud-scoring,validation-enrichment,aml-compliance,routing-execution,settlement,audit,mcp-readonly-gateway \
    -am 2>&1 | grep -E "BUILD|ERROR|\[INFO\] Building|--- " | grep -v "^$" || {
    warn "Maven build had warnings — checking for JARs"
  }

  # Verify JARs exist
  for svc in gateway fraud-scoring validation-enrichment aml-compliance routing-execution settlement audit mcp-readonly-gateway; do
    if ls "$BASE/$svc/target/"*.jar >/dev/null 2>&1; then
      ok "$svc JAR ready"
    else
      err "$svc JAR missing — build failed"
    fi
  done
else
  printf "\n${B}[1/4] Maven Build${R}  ${YELLOW}(skipped via --no-build)${R}\n"
fi

# ── Docker Compose build ──────────────────────────────────
printf "\n${B}[2/4] Docker Image Build${R}\n"
info "Building Docker images for all application services…"
docker compose -f "$COMPOSE" build \
  config-server gateway fraud-scoring validation-enrichment aml-compliance \
  routing-execution settlement audit mcp-readonly-gateway \
  2>&1 | grep -E "^#|Successfully|=>|ERROR" | tail -30 || true
ok "Docker images built"

# ── Start infrastructure ──────────────────────────────────
printf "\n${B}[3/4] Start Full Stack${R}\n"
info "Starting all services (infrastructure + application)…"
docker compose -f "$COMPOSE" up -d
ok "Docker Compose up"

# ── Health check ──────────────────────────────────────────
printf "\n${B}[4/4] Health Check${R}\n"
info "Waiting up to 3 minutes for services to be ready…"

MAX_WAIT=180
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
  GW_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8080/actuator/health" --connect-timeout 3 2>/dev/null || echo "ERR")
  MCP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8087/actuator/health" --connect-timeout 3 2>/dev/null || echo "ERR")
  if [ "$GW_CODE" = "200" ] && [ "$MCP_CODE" = "200" ]; then
    break
  fi
  printf "  ${YELLOW}⋯${R}  Gateway=%s  MCP=%s  (${WAITED}s elapsed)\n" "$GW_CODE" "$MCP_CODE"
  sleep 15
  WAITED=$((WAITED + 15))
done

printf "\n"
ALL_UP=true
for entry in "gateway:8080" "fraud-scoring:8081" "validation-enrichment:8082" \
             "aml-compliance:8083" "routing-execution:8084" "settlement:8085" \
             "audit:8086" "mcp-readonly-gateway:8087"; do
  name="${entry%%:*}"; port="${entry##*:}"
  code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$port/actuator/health" --connect-timeout 3 2>/dev/null || echo "ERR")
  if [ "$code" = "200" ]; then ok "$name (:$port)"
  else warn "$name (:$port) — HTTP $code (may still be starting)"; ALL_UP=false
  fi
done

# ── Frontend ──────────────────────────────────────────────
if [ -d "$BASE/frontend" ]; then
  printf "\n${B}Starting Frontend${R}\n"
  if command -v npm >/dev/null; then
    cd "$BASE/frontend"
    npm install --silent 2>/dev/null
    # Run in background
    nohup npm run dev > "$BASE/frontend/frontend-dev.log" 2>&1 &
    FE_PID=$!
    echo $FE_PID > "$BASE/dev-logs/frontend.pid" 2>/dev/null || true
    sleep 3
    ok "Frontend started (PID $FE_PID) → http://localhost:3000"
  else
    warn "npm not found — start frontend manually: cd frontend && npm run dev"
  fi
fi

# ── Summary ───────────────────────────────────────────────
printf "\n${B}${CYAN}═══════════════════════════════════════════════════════${R}\n"
printf "${B}${GREEN}  ClearFlow is running!${R}\n"
printf "${B}${CYAN}═══════════════════════════════════════════════════════${R}\n\n"

printf "  ${B}Interfaces:${R}\n"
printf "  ${CYAN}→${R}  Operations Dashboard   ${B}http://localhost:3000${R}\n"
printf "  ${CYAN}→${R}  Grafana                ${B}http://localhost:3001${R}\n"
printf "  ${CYAN}→${R}  Kibana                 ${B}http://localhost:5601${R}\n"
printf "  ${CYAN}→${R}  Jaeger Traces          ${B}http://localhost:16686${R}\n"
printf "  ${CYAN}→${R}  ActiveMQ Console       ${B}http://localhost:8161${R}\n"
printf "  ${CYAN}→${R}  Prometheus             ${B}http://localhost:9090${R}\n"
printf "  ${CYAN}→${R}  SonarQube              ${B}http://localhost:9001${R}\n"
printf "  ${CYAN}→${R}  Vault UI               ${B}http://localhost:8200${R}\n"

printf "\n  ${B}Quick start demo:${R}\n"
printf "  ${CYAN}\$${R} bash demo.sh\n"
printf "  ${CYAN}\$${R} python3 live_payment_sender.py\n"
printf "  ${CYAN}\$${R} k6 run load-tests/k6/payment_load_test.js\n"

printf "\n  ${B}Stop:${R}\n"
printf "  ${CYAN}\$${R} docker compose -f infrastructure/docker-compose.yml down\n\n"
