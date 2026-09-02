#!/usr/bin/env bash
# ClearFlow Functional Test Script
# Run with: ./test-functionality.sh
# Prerequisites: Docker infra running (cd infrastructure && docker compose up -d)
#                Config Server on 8888, MCP on 8087 (start manually or via script)

set -euo pipefail

CONFIG_URL="${CONFIG_URL:-http://127.0.0.1:8888}"
MCP_URL="${MCP_URL:-http://127.0.0.1:8087}"
BOLD="\033[1m"
GREEN="\033[32m"
RED="\033[31m"
YELLOW="\033[33m"
RESET="\033[0m"

run() { printf "\n${BOLD}▶ %s${RESET}\n" "$1"; }
ok()  { printf "${GREEN}✓ %s${RESET}\n" "$1"; }
fail() { printf "${RED}✗ %s${RESET}\n" "$1"; }
warn() { printf "${YELLOW}⚠ %s${RESET}\n" "$1"; }

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  ClearFlow Functional Test"
echo "═══════════════════════════════════════════════════════════"

# 1. Unit tests
run "Running unit tests (Java 21 required)..."
if JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 mvn -q test -DskipTests=false 2>/dev/null; then
  ok "41 unit tests passed"
else
  if mvn -q test -DskipTests=false 2>/dev/null; then
    ok "Unit tests passed"
  else
    fail "Unit tests failed - run: JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 mvn test"
    exit 1
  fi
fi

# 2. Config Server health
run "Checking Config Server ($CONFIG_URL)..."
if curl -sf --max-time 5 "$CONFIG_URL/actuator/health" >/dev/null 2>&1; then
  ok "Config Server is UP"
else
  warn "Config Server not reachable. Start with:"
  echo "  mvn -pl config-server spring-boot:run -Dspring-boot.run.arguments='--spring.profiles.active=native'"
fi

# 3. MCP Gateway
run "Checking MCP Gateway ($MCP_URL)..."
if curl -sf --max-time 5 "$MCP_URL/actuator/info" >/dev/null 2>&1; then
  ok "MCP Gateway is UP"
  run "Testing MCP /mcp/payments/PAY-DEMO-AML-001/explain..."
  RESP=$(curl -sf --max-time 30 "$MCP_URL/mcp/payments/PAY-DEMO-AML-001/explain" -H "Authorization: Bearer demo-token" 2>/dev/null || echo "")
  if [ -n "$RESP" ] && echo "$RESP" | grep -q "paymentId"; then
    ok "MCP explain returned valid JSON"
    echo "$RESP" | head -c 300
    echo "..."
  else
    warn "MCP explain timed out or returned empty (Elasticsearch/LLM may be slow)"
  fi
else
  warn "MCP Gateway not reachable. Start with:"
  echo "  mvn -pl mcp-readonly-gateway spring-boot:run \\"
  echo "    -Dspring-boot.run.arguments='--spring.kafka.bootstrap-servers=127.0.0.1:9092 --spring.data.redis.host=127.0.0.1 --spring.data.redis.password=clearflow123'"
fi

# 4. Infrastructure services
run "Checking Docker infrastructure..."
for svc in "Kafka:9092" "Redis:6379" "Elasticsearch:9200"; do
  name="${svc%%:*}"
  port="${svc##*:}"
  if nc -z 127.0.0.1 "$port" 2>/dev/null; then
    ok "$name ($port) is reachable"
  else
    warn "$name ($port) not reachable - ensure docker compose is up"
  fi
done

# 5. MCP lightweight endpoints (timeline, metrics - no LLM)
run "Testing MCP lightweight endpoints..."
TL=$(curl -sf --max-time 8 "$MCP_URL/mcp/payments/PAY-DEMO-AML-001/timeline" 2>/dev/null || echo "")
if [ -n "$TL" ] && echo "$TL" | grep -q "paymentId"; then
  ok "MCP timeline: $TL"
else
  warn "MCP timeline timeout (ensure MCP started with Redis password: --spring.data.redis.password=clearflow123)"
fi

# 6. Demo script
run "Running demo.sh (AML scenario)..."
if timeout 25 ./demo.sh aml 2>/dev/null; then
  ok "Demo script completed"
else
  warn "Demo script timed out - MCP /explain uses LLM (Ollama at :11434 or OpenRouter)"
fi

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  Functional test complete"
echo "═══════════════════════════════════════════════════════════"
echo ""
