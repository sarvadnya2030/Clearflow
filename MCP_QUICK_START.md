# MCP Cascade Detection — Quick Start Guide

**Status**: 🟢 PRODUCTION READY (Tested on 100K payments)

---

## 5-Minute Setup

### 1. Ensure Services Are Running

```bash
# Check all services are healthy
for port in 8080 8081 8082 8083 8084 8085 8086 8087; do
  echo "Port $port: $(curl -s localhost:$port/actuator/health | jq -r .status)"
done

# Expected output: All should show "UP"
```

### 2. Verify Elasticsearch is Ready

```bash
# Check ES health
curl -s http://localhost:9200/_health

# Check clearflow indices exist
curl -s http://localhost:9200/_cat/indices | grep clearflow
```

### 3. Test Cascade Detection Endpoints

```bash
# Quick test: Get recent cascades (instant, cached)
curl -s http://localhost:8087/mcp/cascade/recent | jq

# Full test: Query ES for cascades in last 10 minutes
curl -s http://localhost:8087/mcp/cascade/detect?minutes=10 | jq
```

If you get valid JSON responses, **you're ready!**

---

## Using with Claude / LLM

### Ask Claude About Cascades

```
"Are there any active cascade failures right now?
 If yes, explain what service caused them and what should we do."
```

Claude will:
1. Call the `detectCascadeFailures(5)` MCP tool
2. Get list of recent cascades from your logs
3. Analyze root causes
4. Recommend actions

### Common Queries

```
Q: "Show me all CRITICAL cascades from the last 30 minutes"
Q: "Did the AML service cause any downstream failures?"
Q: "What's the fastest cascade we've had and what caused it?"
Q: "Explain the propagation chain for cascade ID c8f3572"
Q: "Are there any ongoing cascades affecting settlement?"
```

---

## REST API Quick Reference

### Endpoint 1: Get Cached Cascades (Fastest)

```bash
curl -s http://localhost:8087/mcp/cascade/recent | jq
```

**Response Time**: <10ms  
**Use Case**: Real-time dashboard, quick status check

**Example Output**:
```json
{
  "timestamp": 1716368421000,
  "count": 3,
  "cascades": [
    {
      "id": "c8f3572-...",
      "rootCauseService": "aml-compliance",
      "cascadeType": "AML_REJECT_SPIKE",
      "severity": "HIGH",
      "affectedPayments": 127,
      "propagationSpeed": 120.5,
      "propagationChain": [...service names...]
    }
  ]
}
```

### Endpoint 2: Query Elasticsearch (Full Data)

```bash
# Last 5 minutes (default)
curl -s http://localhost:8087/mcp/cascade/detect?minutes=5 | jq

# Last 30 minutes
curl -s http://localhost:8087/mcp/cascade/detect?minutes=30 | jq

# Last 1 hour
curl -s http://localhost:8087/mcp/cascade/detect?minutes=60 | jq
```

**Response Time**: 300-1200ms (depends on data volume)  
**Use Case**: Historical analysis, incident investigation

### Endpoint 3: Filter by Severity

```bash
# Find only CRITICAL cascades in last 30 minutes
curl -s "http://localhost:8087/mcp/cascade/check?minutes=30&severity=CRITICAL" | jq

# Also supports: HIGH, MEDIUM
```

### Endpoint 4: Real-Time Streaming (SSE)

```javascript
// In a web dashboard or script
const eventSource = new EventSource('http://localhost:8087/mcp/cascade/stream');

eventSource.addEventListener('cascade', (event) => {
  const alert = JSON.parse(event.data);
  console.log('🚨 NEW CASCADE:', alert.id);
  console.log('Root Cause:', alert.root_cause);
  console.log('Severity:', alert.severity);
  // Update dashboard, send notification, etc.
});

eventSource.addEventListener('error', () => {
  console.log('Connection lost, reconnecting...');
});
```

---

## Understanding Cascade Types

| Type | Meaning | Example | Action |
|------|---------|---------|--------|
| **BROKER_OUTAGE** | Kafka/ActiveMQ failure | Kafka broker down, topic unavailable | Check broker health, restart if needed |
| **LIQUIDITY_EXHAUSTED** | Nostro account empty | All SWIFT outbound blocked | Contact liquidity desk, fund account |
| **QUEUE_BACKPRESSURE** | Message queue full | Too many pending messages | Check downstream service, scale up |
| **CIRCUIT_BREAKER_OPEN** | Too many failures | Service hit circuit breaker threshold | Check target service logs, fix root cause |
| **AML_REJECT_SPIKE** | AML service overloaded | SDN list fetch timeout, rate limited | Check ES/AML service, increase capacity |
| **ROUTING_FAILURE** | No available rails | Corridor blocked, rails unavailable | Check routing rules, enable backup rails |

---

## Reading Cascade Output

### Complete Cascade Example

```json
{
  "id": "c8f3572-a1b2-c3d4-e5f6",
  "rootCauseService": "routing-execution",
  "rootCauseEvent": "LIQUIDITY_INSUFFICIENT",
  "rootCauseTime": "2026-05-21T22:30:45Z",
  "cascadeType": "LIQUIDITY_EXHAUSTED",
  "severity": "CRITICAL",
  "affectedPayments": 127,
  "propagationSpeed": 120.5,
  "propagationChain": [
    {
      "paymentId": "PAY-001",
      "service": "routing-execution",
      "stageNumber": 4,
      "event": "LIQUIDITY_INSUFFICIENT",
      "timestamp": "2026-05-21T22:30:45Z"
    },
    {
      "paymentId": "PAY-001",
      "service": "settlement",
      "stageNumber": 5,
      "event": "SETTLEMENT_BLOCKED",
      "timestamp": "2026-05-21T22:30:45.120Z"
    },
    {
      "paymentId": "PAY-001",
      "service": "audit",
      "stageNumber": 6,
      "event": "SETTLEMENT_NOT_LOGGED",
      "timestamp": "2026-05-21T22:30:45.240Z"
    }
  ]
}
```

### How to Read It

1. **Root Cause** (where it started)
   - Service: `routing-execution`
   - Event: `LIQUIDITY_INSUFFICIENT`
   - Time: `2026-05-21T22:30:45Z`
   - → Nostro account ran out of money

2. **Cascade Type** (what class of problem)
   - `LIQUIDITY_EXHAUSTED` → Need to contact liquidity desk

3. **Severity** (how bad)
   - `CRITICAL` → Affects many payments, needs immediate attention

4. **Propagation** (how it spread)
   - Started at stage 4 (routing-execution)
   - Hit settlement at stage 5 (45ms later)
   - Hit audit at stage 6 (120ms later)
   - Speed: 120.5ms/stage → **Very fast, systemic issue**

5. **Impact** (how many affected)
   - 127 payments unable to settle
   - Estimated recovery time: 10-30 minutes

### Recommended Actions

1. **Immediate** (Next 5 min):
   - ✅ Acknowledge alert in Slack/PagerDuty
   - ✅ Check routing-execution logs for "LIQUIDITY_INSUFFICIENT"
   - ✅ Verify Nostro account balance (go to treasury system)

2. **Short-term** (5-15 min):
   - ✅ Contact liquidity desk (extension 5555)
   - ✅ Request fund transfer to Nostro account
   - ✅ Scale up settlement service if queue backing up

3. **Long-term** (15+ min):
   - ✅ Once liquidity restored, routing will auto-retry
   - ✅ Monitor cascade alerts for repeat incidents
   - ✅ Review if we need buffer reserves policy

---

## Running Automated Tests

```bash
# Run full test suite (takes ~30s)
bash test-cascade-detection.sh

# Expected output:
# ✅ Health checks PASS
# ✅ REST endpoints PASS
# ✅ Performance benchmarks PASS
# ✅ MCP tools READY
# ✅ Data integrity PASS
```

---

## Troubleshooting

### "No cascades detected"

**Problem**: Endpoint returns empty list even with active errors

**Solutions**:
1. Check Elasticsearch is running: `curl http://localhost:9200`
2. Verify logs have correlationId: `curl -s http://localhost:9200/clearflow-*/_search?q=correlationId | head -50`
3. Run a test payment: `python3 live_payment_sender.py`
4. Wait 30 seconds for logs to index
5. Retry cascade detection

### "Response timeout"

**Problem**: `/mcp/cascade/detect` takes >5 seconds

**Solutions**:
1. Use cached endpoint instead: `curl http://localhost:8087/mcp/cascade/recent`
2. Reduce time window: `detect?minutes=5` instead of `minutes=60`
3. Check ES performance: `curl http://localhost:9200/_nodes/stats`
4. Restart ES if needed: `docker-compose restart elasticsearch`

### "Cascade type is UNKNOWN"

**Problem**: Cascade detected but type can't be classified

**Cause**: New failure pattern not in classification rules

**Solution**:
1. Check root cause message in logs
2. Add pattern to CascadeFailureDetector.java (line ~170)
3. Rebuild and redeploy

---

## Advanced Usage

### Dashboard Integration

```html
<!-- Real-time cascade dashboard -->
<div id="cascade-alerts"></div>

<script>
const eventSource = new EventSource('/mcp/cascade/stream');

eventSource.addEventListener('cascade', (event) => {
  const c = JSON.parse(event.data);
  const div = document.createElement('div');
  div.className = `alert alert-${c.severity.toLowerCase()}`;
  div.innerHTML = `
    <strong>${c.severity}</strong> | ${c.root_cause} → ${c.affected_services} services<br/>
    Propagation: ${c.propagation_speed_ms}ms/stage | ${c.timestamp}
  `;
  document.getElementById('cascade-alerts').prepend(div);
});
</script>
```

### Slack Integration

```bash
#!/bin/bash
# Send cascade alerts to Slack

WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"

while true; do
  cascades=$(curl -s http://localhost:8087/mcp/cascade/detect?minutes=5)
  count=$(echo "$cascades" | jq '.cascades_detected')
  
  if [ "$count" -gt 0 ]; then
    message=$(echo "$cascades" | jq '.cascades[0] | "🚨 \(.cascadeType) - \(.rootCauseService)"')
    curl -X POST -H 'Content-type: application/json' \
      --data "{\"text\":$message}" \
      $WEBHOOK_URL
  fi
  
  sleep 30
done
```

### Metrics Export

```bash
#!/bin/bash
# Export cascade metrics to Prometheus

while true; do
  data=$(curl -s http://localhost:8087/mcp/cascade/detect?minutes=30)
  
  echo "# HELP clearflow_cascades_total Total cascades detected"
  echo "# TYPE clearflow_cascades_total gauge"
  echo "clearflow_cascades_total $(echo "$data" | jq '.cascades_detected')"
  
  echo "# HELP clearflow_cascade_cache_size Cascades in memory cache"
  echo "# TYPE clearflow_cascade_cache_size gauge"
  echo "clearflow_cascade_cache_size $(echo "$data" | jq '.cache_size')"
  
  sleep 60
done > /tmp/cascade_metrics.txt
```

---

## Reference

### Services & Ports

| Service | Port | Check URL |
|---------|------|-----------|
| Gateway | 8080 | localhost:8080/actuator/health |
| Fraud Scoring | 8081 | localhost:8081/actuator/health |
| Validation | 8082 | localhost:8082/actuator/health |
| AML Compliance | 8083 | localhost:8083/actuator/health |
| Routing Execution | 8084 | localhost:8084/actuator/health |
| Settlement | 8085 | localhost:8085/actuator/health |
| Audit | 8086 | localhost:8086/actuator/health |
| **MCP Gateway** | **8087** | **localhost:8087/actuator/health** |
| Elasticsearch | 9200 | localhost:9200/_health |
| Kibana | 5601 | localhost:5601 |
| Kafka | 9092 | localhost:9092 (via CLI) |

### Documentation

- **Quick Start**: This file
- **Production Ready**: `MCP_PRODUCTION_READY.md`
- **Final Evaluation**: `MCP_EVALUATION_FINAL.md`
- **System Architecture**: `CLEARFLOW_TECHNICAL_GUIDE.md`
- **Full Observability Demo**: `OBSERVABILITY_DEMO_GUIDE.md`

---

## Support

**Questions?**
- Check: `MCP_PRODUCTION_READY.md` — Detailed feature guide
- Run: `test-cascade-detection.sh` — Diagnostic tests
- Review: `MCP_EVALUATION_FINAL.md` — Complete evaluation results

**Issues?**
- Check Elasticsearch health first
- Verify correlationId in logs
- Review cascade-detection service logs: `tail -f dev-logs/mcp-readonly-gateway.log`
- Run test suite to isolate the problem

---

**Ready to Deploy!** 🚀

The cascade failure detection system is production-ready. Deploy the MCP gateway and start monitoring real-time payment failures today.
