#!/bin/bash
# Provision Grafana dashboards after startup

GRAFANA_URL="http://localhost:3001"
GRAFANA_AUTH="admin:admin"

echo "Provisioning Grafana dashboards..."

# Wait for Grafana to be ready
for i in {1..30}; do
  if curl -s "$GRAFANA_URL/api/health" >/dev/null 2>&1; then
    echo "✓ Grafana ready"
    break
  fi
  sleep 2
done

# Import dashboards from JSON files
for dashboard_file in provisioning/dashboards/clearflow-*.json; do
  dashboard_name=$(basename "$dashboard_file" .json)
  echo "  Importing $dashboard_name..."
  
  curl -X POST "$GRAFANA_URL/api/dashboards/db" \
    -H "Content-Type: application/json" \
    -u "$GRAFANA_AUTH" \
    -d @"$dashboard_file" \
    --silent --output /dev/null || echo "    (may already exist)"
done

echo "✓ Grafana dashboards provisioned"
echo ""
echo "Dashboards available at:"
echo "  http://localhost:3001"
echo ""
echo "Default credentials: admin / admin"
