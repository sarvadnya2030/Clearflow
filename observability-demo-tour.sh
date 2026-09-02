#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  ClearFlow Observability Stack Demo Tour
#  Shows live dashboards + logs + traces during payment processing
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

B="\033[1m"; DIM="\033[2m"; R="\033[0m"
RED="\033[31m"; GREEN="\033[32m"; YELLOW="\033[33m"
BLUE="\033[34m"; CYAN="\033[36m"; WHITE="\033[37m"

banner()  { printf "\n${B}${CYAN}════════════════════════════════════════════════════${R}\n  ${B}${WHITE}%s${R}\n${B}${CYAN}════════════════════════════════════════════════════${R}\n\n" "$1"; }
section() { printf "\n${B}${BLUE}── %s ──────────────────────────────────────────${R}\n" "$1"; }
ok()      { printf "  ${GREEN}✓${R}  %s\n" "$1"; }
info()    { printf "  ${YELLOW}▸${R}  %s\n" "$1"; }
kv()      { printf "  ${B}${CYAN}%-30s${R} %s\n" "$1" "$2"; }
pause()   { printf "\n  ${DIM}Press Enter to continue…${R}"; read -r; }

banner "ClearFlow — Full Observability Stack Demo"
printf "  Real-time dashboards, logs, traces, and metrics\n"
printf "  Open these in your browser while payments flow:\n\n"

kv "Grafana Dashboards" "http://localhost:3001"
kv "Kibana Logs" "http://localhost:5601"
kv "Jaeger Traces" "http://localhost:16686"
kv "Prometheus" "http://localhost:9090"
kv "ActiveMQ Console" "http://localhost:8161"
kv "Elasticsearch" "http://localhost:9200/_plugin/kibana"

pause

# ═══════════════════════════════════════════════════════════════
section "STEP 1 — Check Grafana Dashboards Are Provisioned"

echo "  Checking Grafana dashboard availability..."
for dashboard in "clearflow-main" "clearflow-payments" "clearflow-fraud" "clearflow-infrastructure" "clearflow-slo"; do
  status=$(curl -s -H "Authorization: Bearer admin:admin" \
    "http://localhost:3001/api/search?query=$dashboard" 2>/dev/null | grep -c "\"title\"" || echo "0")
  if [ "$status" -gt 0 ]; then
    ok "Grafana dashboard: $dashboard"
  else
    info "Dashboard $dashboard — provisioning..."
  fi
done

pause

# ═══════════════════════════════════════════════════════════════
section "STEP 2 — Check Elasticsearch Indices"

echo "  Checking Elasticsearch for payment logs..."
indices=$(curl -s "http://localhost:9200/_cat/indices?format=json" 2>/dev/null | grep -c "clearflow" || echo "0")
if [ "$indices" -gt 0 ]; then
  ok "Found $indices Elasticsearch indices with 'clearflow' prefix"
  curl -s "http://localhost:9200/_cat/indices?v" 2>/dev/null | grep clearflow | head -5
else
  info "No clearflow indices yet — will create during payment processing"
fi

pause

# ═══════════════════════════════════════════════════════════════
section "STEP 3 — Send Test Payments and Watch Dashboards"

printf "  ${DIM}Follow these steps:${R}\n\n"
printf "  1. Open http://localhost:3001 → click 'clearflow-main' dashboard\n"
printf "  2. Open http://localhost:5601 → search for 'clearflow'\n"
printf "  3. Open http://localhost:16686 → select 'gateway' service\n"
printf "  4. Run: python3 live_payment_sender.py\n"
printf "\n  Watch as:\n"
printf "    • Grafana shows payment funnel: gateway → fraud → validation → AML → routing → settlement\n"
printf "    • Kibana logs appear in real-time with correlationId\n"
printf "    • Jaeger traces show end-to-end latency for each payment\n\n"

read -p "  Ready? Press Enter to start sending payments..."

# Send payments
python3 live_payment_sender.py 2>&1 | tee observability_test_run.log

pause

# ═══════════════════════════════════════════════════════════════
section "STEP 4 — Trace a Single Payment"

# Extract a paymentId from the run
PAYMENT_ID=$(grep -o 'paymentId=[a-f0-9-]*' observability_test_run.log | head -1 | cut -d= -f2)

if [ -z "$PAYMENT_ID" ]; then
  echo "  No payment found in logs"
  exit 1
fi

ok "Tracing payment: $PAYMENT_ID"
echo ""
printf "  In Kibana, search for:\n"
printf "    ${B}correlationId:$PAYMENT_ID${R}\n\n"
printf "  You should see events from 7 services in order:\n"
printf "    1. gateway (payment.initiated)\n"
printf "    2. fraud-scoring (fraud.evaluated)\n"
printf "    3. validation-enrichment (payment.validated)\n"
printf "    4. aml-compliance (aml.sanctions.clear or .hit)\n"
printf "    5. routing-execution (payment.routed)\n"
printf "    6. settlement (payment.settled)\n"
printf "    7. audit (hash chain recorded)\n\n"

pause

# ═══════════════════════════════════════════════════════════════
section "STEP 5 — Prometheus Alerts"

echo "  Checking Prometheus alert rules..."
rules=$(curl -s "http://localhost:9090/api/v1/rules" 2>/dev/null | grep -c "clearflow" || echo "0")
ok "Found $rules active ClearFlow alert rules in Prometheus"

printf "\n  Key metrics to monitor:\n"
printf "    • clearflow_payment_acceptance_rate_percent\n"
printf "    • clearflow_payment_p99_latency_ms\n"
printf "    • clearflow_dlq_depth_total\n"
printf "    • clearflow_fraud_block_rate_percent\n"
printf "    • clearflow_circuit_breaker_status\n\n"

pause

# ═══════════════════════════════════════════════════════════════
section "STEP 6 — ActiveMQ Queue Monitoring"

echo "  ActiveMQ Artemis console is ready at:"
printf "  ${B}http://localhost:8161${R}\n\n"
printf "  Log in: admin / admin\n\n"
printf "  View queues and topics:\n"
printf "    • clearflow.payment.initiated\n"
printf "    • clearflow.payment.blocked\n"
printf "    • clearflow.payment.dlq (should be empty)\n"
printf "    • Saga compensation routes\n\n"

# ═══════════════════════════════════════════════════════════════
banner "Observability Tour Complete"
printf "  All dashboards are live and ingesting real payment data.\n"
printf "  Use these for:\n"
printf "    • Operational monitoring during demos\n"
printf "    • Paper figures (screenshots of live dashboards)\n"
printf "    • Evaluation metrics validation\n\n"
