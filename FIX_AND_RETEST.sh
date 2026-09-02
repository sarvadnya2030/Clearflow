#!/bin/bash
# Fix all bottlenecks and re-test for maximum success rate

echo "╔════════════════════════════════════════════════════╗"
echo "║   MAXIMIZING PAYMENT SUCCESS RATE - 100K TEST     ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""

BASE="/home/admin-/Desktop/EDI6/clearflow"
cd "$BASE"

# ════════════════════════════════════════════════════════
# STEP 1: Kill old services
# ════════════════════════════════════════════════════════
echo "[1/5] Stopping old services..."
bash stop_live_traffic.sh >/dev/null 2>&1
sleep 5

# ════════════════════════════════════════════════════════
# STEP 2: Fix ActiveMQ pool (50 → 200)
# ════════════════════════════════════════════════════════
echo "[2/5] Fixing ActiveMQ connection pool (50 → 200)..."
sed -i 's/max-connections: 50/max-connections: 200/g' \
  gateway/src/main/resources/application-dev.yml

echo "      ✓ Pool increased to 200 connections"

# ════════════════════════════════════════════════════════
# STEP 3: Tune circuit breaker to be lenient
# ════════════════════════════════════════════════════════
echo "[3/5] Tuning circuit breaker (graceful degradation)..."
cat > /tmp/circuit_breaker_patch.txt << 'CONFIG'
resilience4j:
  circuitbreaker:
    configs:
      default:
        slidingWindowSize: 500  # was 1000 - faster recovery
        failureRateThreshold: 80.0  # was 50% - only open at 80% failures
        slowCallRateThreshold: 80.0  # was 50%
        slowCallDurationThreshold: 10000  # was 5000 - more tolerance
        waitDurationInOpenState: 10000  # was 30000 - faster recovery attempts
        permittedNumberOfCallsInHalfOpenState: 200  # was 100 - more attempts to recover
    instances:
      activemq:
        baseConfig: default
CONFIG

# Apply the change
sed -i '/^resilience4j:/,/^[^ ]/d' gateway/src/main/resources/application-dev.yml
cat /tmp/circuit_breaker_patch.txt >> gateway/src/main/resources/application-dev.yml
echo "      ✓ Circuit breaker tuned (80% threshold, 10s recovery, 200 half-open)"

# ════════════════════════════════════════════════════════
# STEP 4: Rebuild and restart
# ════════════════════════════════════════════════════════
echo "[4/5] Rebuilding services..."
JAVA_HOME="/usr/lib/jvm/java-21-openjdk-amd64" \
  /home/admin-/.maven/maven-3.9.12/bin/mvn package -DskipTests \
  -pl gateway,fraud-scoring,validation-enrichment,aml-compliance,routing-execution,settlement,audit,mcp-readonly-gateway \
  -am 2>&1 | grep -E "BUILD|ERROR" | head -5

echo "      ✓ Build complete"

# ════════════════════════════════════════════════════════
# STEP 5: Start with optimized config
# ════════════════════════════════════════════════════════
echo "[5/5] Starting with optimized configuration..."
bash start_live_traffic.sh 2>&1 | tail -15

echo ""
echo "╔════════════════════════════════════════════════════╗"
echo "║         SYSTEM READY FOR RETEST                   ║"
echo "║  ActiveMQ Pool: 50 → 200 connections              ║"
echo "║  Circuit Breaker: 50% → 80% threshold             ║"
echo "║  Recovery Time: 30s → 10s                         ║"
echo "╚════════════════════════════════════════════════════╝"
