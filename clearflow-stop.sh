#!/bin/bash
# clearflow-stop.sh — Stop all ClearFlow microservices
BASE="/home/admin-/Desktop/EDI6/clearflow"
LOGS="$BASE/dev-logs"

echo "Stopping ClearFlow microservices..."
for svc in fraud-scoring validation-enrichment aml-compliance routing-execution settlement audit gateway mcp-readonly-gateway fraud-model; do
  if [ -f "$LOGS/$svc.pid" ]; then
    pid=$(cat "$LOGS/$svc.pid")
    if kill "$pid" 2>/dev/null; then
      echo "  stopped $svc (PID $pid)"
    fi
    rm -f "$LOGS/$svc.pid"
  fi
done

pkill -f "fraud-scoring-1.0.0\|validation-enrichment-1.0.0\|aml-compliance-1.0.0\|routing-execution-1.0.0\|settlement-1.0.0\|audit-1.0.0\|gateway-1.0.0\|mcp-readonly-gateway-1.0.0\|fraud_model_server" 2>/dev/null || true

echo "Done. Infrastructure (Docker) left running."
echo "To stop infra: cd $BASE/infrastructure && docker compose down"
