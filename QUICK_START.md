# Real-Time Payment Cascade Intelligence — Quick Start Guide

## One-Command Startup

```bash
cd /home/admin-/Desktop/EDI6/clearflow
bash start_live_traffic.sh
```

That's it. All 8 services will be UP in ~2 minutes.

---

## What That Does

1. **Starts infrastructure** (Kafka, Redis, ActiveMQ, MongoDB, Cassandra, Elasticsearch)
2. **Creates Kafka topics** (if needed)
3. **Builds all services** with Maven (skips tests)
4. **Starts all 8 microservices** on ports 8080–8087
5. **Health checks** all services

---

## Services & Ports

| Service | Port | Purpose |
|---------|------|---------|
| `gateway` | 8080 | Payment entry point |
| `fraud-scoring` | 8081 | ML fraud detection |
| `validation-enrichment` | 8082 | IBAN/BIC/embargo checks |
| `aml-compliance` | 8083 | Sanctions & PEP screening |
| `routing-execution` | 8084 | Rail selection (CHIPS, FEDWIRE, etc.) |
| `settlement` | 8085 | Double-entry accounting |
| `audit` | 8086 | SHA-256 hash chain |
| `mcp-readonly-gateway` | 8087 | LLM API + root cause analysis |

---

## If Services Don't Start

### Check for Issues
```bash
# View individual service logs
tail -f /home/admin-/Desktop/EDI6/clearflow/dev-logs/gateway.log
tail -f /home/admin-/Desktop/EDI6/clearflow/dev-logs/fraud-scoring.log

# Check service status
curl http://localhost:8080/actuator/health
curl http://localhost:8081/actuator/health
```

### Common Problems & Fixes

**Problem: Kafka topics not found**
```bash
# Manually create topics:
cd /home/admin-/Desktop/EDI6/clearflow/infrastructure
docker compose exec -T kafka kafka-topics --bootstrap-server kafka:9092 --create --if-not-exists --topic clearflow.payment.initiated --partitions 5 --replication-factor 1
```

**Problem: ActiveMQ connection pool exhausted**
- Already fixed in config (pool size: 200)
- File: `gateway/src/main/resources/application-dev.yml`

**Problem: Services won't start (old process still running)**
```bash
# Kill all old services
pkill -f "gateway.*jar" || true
pkill -f "fraud-scoring.*jar" || true
# Then run start_live_traffic.sh again
```

**Problem: Infrastructure containers down**
```bash
cd /home/admin-/Desktop/EDI6/clearflow/infrastructure
docker compose up -d
```

---

## Test Payments

After services are UP, send test payments:

```bash
# Simple test (15 payments)
python3 live_payment_sender.py

# Heavy load test (100,000 payments)
python3 batch_100k.py
```

---

## Stop Everything

```bash
bash /home/admin-/Desktop/EDI6/clearflow/stop_live_traffic.sh
```

---

## Troubleshooting Checklist

- [ ] Infrastructure running: `docker compose ps` (should show 7 containers UP)
- [ ] Kafka topics exist: check via `docker compose exec -T kafka kafka-topics --list`
- [ ] Gateway healthy: `curl localhost:8080/actuator/health`
- [ ] Fraud-scoring healthy: `curl localhost:8081/actuator/health`
- [ ] Logs clean (no `UNKNOWN_TOPIC_OR_PARTITION` errors in recent logs)

---

## Key Environment Variables

All services use the `dev` Spring profile:
- `SPRING_PROFILES_ACTIVE=dev`
- `JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64`

Config servers will connect to:
- Kafka: `localhost:29092`
- ActiveMQ: `localhost:61616`
- Redis: `localhost:6379` (password: `clearflow123`)
- MongoDB: `localhost:27017`
- Cassandra: `localhost:9042`
- Elasticsearch: `localhost:9200`
- Oracle/H2: in-memory (dev profile)

---

## Next Steps

Once services are UP:
1. ✓ Run `python3 live_payment_sender.py` to verify all 8 stages
2. ✓ Run `python3 batch_100k.py` for load test
3. Check MCP AI gateway: `curl http://localhost:8087/mcp/payments/PAY-DEMO-AML-001/explain`
4. View Elasticsearch logs: Open Kibana at http://localhost:5601
