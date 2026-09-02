# Real-Time Payment Cascade Intelligence — Startup Guide & Incident Log

> Reference this file at the start of any session before touching Real-Time Payment Cascade Intelligence.
> Path: `/home/admin-/Desktop/EDI6/clearflow/STARTUP_GUIDE.md`

---

## TL;DR — Start Everything

```bash
cd /home/admin-/Desktop/EDI6/clearflow
bash clearflow-start.sh
```

That's the only command you need. It handles infra, build, all 8 services, and health checks.

**Do NOT use `start_live_traffic.sh` anymore** — it's the old script and does not have the fixes.

---

## Script Reference

| Script | Purpose |
|--------|---------|
| `bash clearflow-start.sh` | Full startup: infra + build + 8 services + health check |
| `bash clearflow-start.sh --skip-build` | Skip Maven build (use existing JARs — saves 3-4 min) |
| `bash clearflow-start.sh --skip-infra` | Skip Docker infra (already running) |
| `bash clearflow-start.sh --skip-build --skip-infra` | Only start/restart the Java services |
| `bash clearflow-stop.sh` | Stop all 8 microservices (leaves Docker infra running) |

---

## Services & Ports

| Service | Port | Role |
|---------|------|------|
| `gateway` | 8080 | Payment entry point (WebFlux, OAuth2) |
| `fraud-scoring` | 8081 | LightGBM + heuristic fraud detection |
| `validation-enrichment` | 8082 | IBAN/BIC/embargo checks (Apache Camel) |
| `aml-compliance` | 8083 | Sanctions + PEP screening (Camunda) |
| `routing-execution` | 8084 | Rail selection, nostro liquidity |
| `settlement` | 8085 | Double-entry accounting |
| `audit` | 8086 | SHA-256 hash chain (Cassandra) |
| `mcp-readonly-gateway` | 8087 | LLM/AI read-only API |
| `fraud-model-server` | 8091 | Python LightGBM server (optional) |

**Expected health check output:**
```
  ✓ fraud-scoring (:8081)
  ✓ validation-enrichment (:8082)
  ✓ aml-compliance (:8083)
  ✓ routing-execution (:8084)
  ✓ settlement (:8085)
  ✓ audit (:8086)
  ✓ gateway (:8080)
  ✓ mcp-readonly-gateway (:8087)
  ✅ ALL 8 SERVICES UP
```

---

## Infrastructure (Docker)

All infra runs via Docker Compose in `/home/admin-/Desktop/EDI6/clearflow/infrastructure/`.

| Container | Port(s) | Purpose |
|-----------|---------|---------|
| Kafka | 29092 (external), 9092 (internal) | Event streaming |
| ZooKeeper | 2181 | Kafka coordination |
| ActiveMQ Artemis | 61616 | JMS broker |
| Redis | 6379 | Cache + idempotency + embargo list |
| MongoDB | 27017 | Payment document store |
| Cassandra | 9042 | Audit + settlement ledger |
| Elasticsearch | 9200 | Log aggregation |
| Logstash | 5044 | Log pipeline |
| Kibana | 5601 | Log dashboards |
| Jaeger | 16686 | Distributed tracing UI |
| Vault | 8200 | Secrets (dev mode) |

**Kafka topics** (9 partitions each): `clearflow.payment.initiated`, `clearflow.fraud.evaluated`, `clearflow.payment.blocked`, `clearflow.payment.validated`, `clearflow.payment.rejected`, `clearflow.aml.sanctions.clear`, `clearflow.aml.sanctions.hit`, `clearflow.compliance.alerts`, `clearflow.payment.routed`, `clearflow.payment.failed`, `clearflow.payment.settled`, `clearflow.analytics.settlement`, `clearflow.mcp.access.log`, plus `.dlq` variants.

---

## Quick Diagnostics

```bash
# Check which services are healthy
for p in 8080 8081 8082 8083 8084 8085 8086 8087; do
  echo -n ":$p "
  curl -s localhost:$p/actuator/health 2>/dev/null \
    | python3 -c 'import sys,json; print(json.load(sys.stdin)["status"])' 2>/dev/null \
    || echo DOWN
done

# Tail a service log
tail -f /home/admin-/Desktop/EDI6/clearflow/dev-logs/gateway.log \
  | python3 -c "import sys,json; [print(json.loads(l).get('level',''), json.loads(l).get('message','')[:200]) for l in sys.stdin if l.strip()]"

# Check if a service process is alive
cat /home/admin-/Desktop/EDI6/clearflow/dev-logs/gateway.pid | xargs kill -0 && echo alive || echo dead

# Kafka topic list
cd /home/admin-/Desktop/EDI6/clearflow/infrastructure
docker compose exec -T kafka kafka-topics --bootstrap-server kafka:9092 --list | grep clearflow
```

---

## Post-Startup Tests

```bash
# Smoke test — 15 payments through full 7-stage pipeline
python3 /home/admin-/Desktop/EDI6/clearflow/live_payment_sender.py
# Expected: 15 accepted (HTTP 202), correlationId visible in all service logs

# Load test — 100,000 payments
python3 /home/admin-/Desktop/EDI6/clearflow/batch_100k.py
# Expected: ~95% accept (5K AML-rejected), p99 < 250ms, 0 routing failures

# Observability dashboard
streamlit run /home/admin-/Desktop/EDI6/clearflow/observability_dashboard.py
```

---

## Incident Log

### Incident 1 — All 8 Services Crash at Startup (2026-05-09)

**Symptom:**
All 8 services fail immediately with `HTTP 000ERR` on health check. Stderr logs empty. Log files show crash within 10 seconds.

**Error in log:**
```
ERROR Application run failed
Caused by: NoClassDefFoundError:
  io/opentelemetry/exporter/internal/otlp/traces/LowAllocationTraceRequestMarshaler
```

**Root cause:**
`pom.xml` (parent, line ~78) had `opentelemetry-exporter-otlp` pinned to version `1.40.0`, but Spring Boot 3.3.2's BOM supplies `opentelemetry-exporter-otlp-common` at `1.37.0`. The 1.40.0 exporter references the class `LowAllocationTraceRequestMarshaler` which was restructured between those two versions — class not found at runtime → all services crash before Tomcat can start.

**Fix applied:**
In `pom.xml`, changed:
```xml
<groupId>io.opentelemetry</groupId>
<artifactId>opentelemetry-exporter-otlp</artifactId>
<version>1.40.0</version>   <!-- was this -->
<version>1.37.0</version>   <!-- changed to this -->
```
Then rebuilt all 8 services:
```bash
cd /home/admin-/Desktop/EDI6/clearflow
JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
  /home/admin-/.maven/maven-3.9.12/bin/mvn package -DskipTests --no-transfer-progress \
  -pl common,gateway,fraud-scoring,validation-enrichment,aml-compliance,routing-execution,settlement,audit,mcp-readonly-gateway -am
```

**Verify fix:** `jar tf validation-enrichment/target/validation-enrichment-1.0.0.jar | grep opentelemetry-exporter-otlp` should show `1.37.0` for both `-otlp` and `-otlp-common`.

---

### Incident 2 — `validation-enrichment` Hangs Forever After MongoDB Init (2026-05-09)

**Symptom:**
7 of 8 services start fine. `validation-enrichment` (port 8082) process is alive but never responds to `/actuator/health`. Log stops at exactly this line and never progresses:
```
INFO Monitor thread successfully connected to server with description ServerDescription{address=localhost:27017...
```
Process runs for 30+ minutes with no further log output.

**Diagnosis:**
Used `jstack <pid>` to get a thread dump. Main thread stack:
```
at com.clearflow.validation.config.EmbargoDataLoader.load(EmbargoDataLoader.java:21)
at io.lettuce.core.DefaultConnectionFuture.get(DefaultConnectionFuture.java:69)
at io.lettuce.core.AbstractRedisClient.getConnection(AbstractRedisClient.java:345)
at io.lettuce.core.RedisClient.connect(RedisClient.java:215)
at org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory$SharedConnection.getConnection
at org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory.doInLock
```
Meanwhile the Netty event loop thread was stuck in:
```
at io.lettuce.core.metrics.MicrometerCommandLatencyRecorder.recordCommandLatency
at io.lettuce.core.protocol.CommandHandler.decode
at io.netty.channel.epoll.EpollEventLoop.run
```

**Root cause:**
`EmbargoDataLoader.@PostConstruct` called `StringRedisTemplate.opsForSet().add()` during Spring bean initialization phase. Internally Lettuce's `SharedConnection.doInLock()` acquired a synchronization lock and blocked the **main thread** waiting for Netty's TCP connection future to complete. The **Netty event loop thread** was simultaneously recording Micrometer metrics — unable to signal the connection future. Classic deadlock: main thread waiting for Netty, Netty thread blocked by a downstream operation, neither can proceed.

Redis itself was healthy (`redis-cli ping` → PONG). This was a Lettuce/Spring Data Redis deadlock during startup, not a Redis connectivity issue.

**Fix applied:**
Changed `EmbargoDataLoader` from `@PostConstruct` to `@EventListener(ApplicationReadyEvent.class)`:

```java
// BEFORE (causes deadlock):
@PostConstruct
public void load() {
    redisTemplate.opsForSet().add("embargoed:countries", ...);
}

// AFTER (safe — runs after full context init):
@EventListener(ApplicationReadyEvent.class)
public void load() {
    try {
        redisTemplate.opsForSet().add("embargoed:countries", ...);
        log.info("Embargo country list loaded into Redis (7 countries)");
    } catch (Exception ex) {
        log.warn("EmbargoDataLoader failed: {}", ex.getMessage());
    }
}
```

File: `validation-enrichment/src/main/java/com/clearflow/validation/config/EmbargoDataLoader.java`

**Result:** `validation-enrichment` now starts in ~13 seconds. Embargo data loads cleanly after context is up.

**General rule:** Never call Redis, Kafka, or any external I/O inside `@PostConstruct`. Use `@EventListener(ApplicationReadyEvent.class)` instead. `@PostConstruct` runs during Spring's synchronous bean init phase where connection pools are not yet fully initialized, making deadlocks possible.

---

## Known Good State (2026-05-09)

- All 8 services UP after `bash clearflow-start.sh`
- OTel: all jars at 1.37.0 (matches Spring Boot 3.3.2 BOM)
- EmbargoDataLoader: uses `@EventListener`, no deadlock
- Kafka: 9 partitions per topic, 19 topics
- Nostro accounts: 500B per currency (no liquidity drain in 100K test)
- 100K test validated: ~95% accept, p99 < 250ms, 0 routing failures

---

## Environment

```
Java:   /usr/lib/jvm/java-21-openjdk-amd64/bin/java  (Java 21)
Maven:  /home/admin-/.maven/maven-3.9.12/bin/mvn
Logs:   /home/admin-/Desktop/EDI6/clearflow/dev-logs/
JVM:    -Xmx1536m -Xms512m -XX:+UseG1GC -XX:MaxGCPauseMillis=200
Spring: SPRING_PROFILES_ACTIVE=dev
```
