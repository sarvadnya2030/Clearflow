# ClearFlow — Run & Functional Test Guide

## Quick Start (Local Testing)

### 1. Start Infrastructure (Docker)

```bash
cd infrastructure
docker compose up -d
```

Wait 2–3 minutes for Kafka, Redis, Oracle, Cassandra, etc. to be healthy.

### 2. Start Config Server

```bash
cd /path/to/clearflow
JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 mvn -pl config-server spring-boot:run \
  -Dspring-boot.run.arguments="--spring.profiles.active=native"
```

Config Server will be available at http://127.0.0.1:8888

### 3. Start MCP Gateway (for AI/demo)

```bash
JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 mvn -pl mcp-readonly-gateway spring-boot:run \
  -Dspring-boot.run.arguments="\
    --spring.config.import=optional:configserver:http://127.0.0.1:8888 \
    --spring.kafka.bootstrap-servers=127.0.0.1:9092 \
    --spring.data.redis.host=127.0.0.1 \
    --spring.data.redis.password=clearflow123 \
    --clearflow.elasticsearch.url=http://127.0.0.1:9200"
```

MCP will be at http://127.0.0.1:8087. Demo data is auto-seeded into Elasticsearch on startup.

### 4. Run Functional Test

```bash
./test-functionality.sh
```

### 5. Run Demo Script

```bash
./demo.sh          # All scenarios
./demo.sh aml      # AML sanctions hit
./demo.sh fraud    # Fraud critical
./demo.sh settled  # Happy path
```

---

## Testing Payment Flow (Full Pipeline)

For end-to-end payment processing you need:

1. **Gateway** — requires Keycloak (OAuth2) at `localhost:8090` or mock JWT
2. **All services** — Config Server, Gateway, Fraud, Validation, AML, Routing, Settlement, Audit

Option A: Fix Docker builds (ensure Spring Boot produces executable jars) and run:

```bash
cd infrastructure && docker compose up -d
```

Option B: Run services locally (each in a separate terminal) with config server at 127.0.0.1:8888 and infrastructure hostnames set to 127.0.0.1.

---

## Manual API Tests

| Endpoint | Command |
|----------|---------|
| Config health | `curl http://127.0.0.1:8888/actuator/health` |
| MCP info | `curl http://127.0.0.1:8087/actuator/info` |
| MCP explain | `curl "http://127.0.0.1:8087/mcp/payments/PAY-DEMO-AML-001/explain" -H "Authorization: Bearer demo-token"` |
| MCP timeline | `curl "http://127.0.0.1:8087/mcp/payments/PAY-DEMO-AML-001/timeline"` |

---

## Unit Tests

```bash
JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 mvn test
```
