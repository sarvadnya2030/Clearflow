#!/bin/bash
BASE="/home/admin-/Desktop/EDI6/clearflow"
LOGS="$BASE/dev-logs"

echo "Stopping ClearFlow microservices..."
for pidfile in "$LOGS"/*.pid; do
  [ -f "$pidfile" ] || continue
  pid=$(cat "$pidfile")
  name=$(basename "$pidfile" .pid)
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid"
    echo "  Stopped $name (PID $pid)"
  fi
  rm -f "$pidfile"
done

echo "Stopping infrastructure containers..."
cd "$BASE/infrastructure"
docker-compose stop zookeeper kafka activemq-artemis redis mongodb cassandra elasticsearch

echo "Done."
