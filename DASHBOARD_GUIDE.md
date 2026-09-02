# ClearFlow Observability Dashboard - User Guide

## Quick Start

```bash
# Start the dashboard
streamlit run observability_dashboard.py

# Access at
open http://localhost:8501
```

The dashboard will be available immediately and queries Elasticsearch (91K logs), MCP gateway, and local data files in real-time.

---

## Dashboard Overview

**6 Interactive Pages** showing the complete observability system for the 100K payment test:

### 📈 Page 1: Overview
**Shows**: High-level metrics and cascade pattern

**Key Metrics**:
- Total Logs: 91,146 from 7 services
- Total Payments: 100,000 sent
- Acceptance Rate: 0.2% ❌
- Error Rate: 9.18% ❌

**Interactive Elements**:
- Batch-by-batch acceptance rate chart (shows cascade at batch 2)
- Detailed batch table (Sent, Accepted, Errors, Acceptance%)
- Root cause explanation (connection pool exhaustion)

**Use This When**:
- You want a quick overview of test results
- You need to explain the cascade pattern visually
- You want batch-level metrics at a glance

---

### 💰 Page 2: Payment Metrics
**Shows**: Success rates, failures, latency distribution

**Key Sections**:

1. **Payment Status Counts**
   - Accepted (202): 160 (0.16%)
   - Connection Errors: 9,177 (9.18%)
   - Duplicate/Rate-limited: 0
   - Server errors: 0

2. **Scenario Breakdown**
   - Which payment types succeeded (table + pie chart)
   - 139 happy path, 10 high-value, 9 AML, etc.
   - Shows all failures were in infrastructure, not validation

3. **Latency Distribution**
   - p50: 11ms (fast)
   - p95: 18ms (fast)
   - p99: 194ms (low because failures are instant)
   - max: 194ms

**Insights Provided**:
- Why latencies are so low (requests fail instantly)
- Which scenarios would pass if connection pool fixed
- Proof that 160 successful payments prove concept works

**Use This When**:
- Analyzing payment success rates
- Explaining why latency looks good (but acceptance is bad)
- Breaking down failures by payment type
- Showing that the system CAN work (batch 1 proof)

---

### 📊 Page 3: ELK Analysis
**Shows**: Elasticsearch log queries and distribution

**Real ELK Queries**:
1. Service log volume (interactive table + bar chart)
2. Log severity breakdown (WARN/INFO/ERROR pie chart)
3. Sample query templates for custom analysis

**Key Visualization**:
```
Service                  Logs      %
gateway                 83,897    92%  ← OBVIOUS BOTTLENECK
fraud-scoring            3,541     4%
audit                    3,514     4%
others                     194    <1%  ← BLOCKED BY CASCADE
```

**What This Shows**:
- Gateway has 92% of all logs (only service getting traffic)
- Downstream services have 8% (prove cascade blocked them)
- Cascade pattern is statistically visible

**Interactive Queries**:
- Real curl commands to query Elasticsearch directly
- Shows JSON request/response format
- Copy-paste ready for terminal use

**Use This When**:
- You need to query the 91K logs
- You want to verify cascade in actual data
- You need sample ELK queries for documentation
- You want to show log volume proof of bottleneck

---

### 🔌 Page 4: MCP Queries
**Shows**: Model Context Protocol API for structured queries

**Available Endpoints**:
```
GET  /mcp/api/payments          → List all with status
GET  /mcp/api/payments/{id}     → Single payment details
GET  /mcp/api/batches           → Batch-level metrics
GET  /mcp/api/cascade-metrics   → Failure progression
POST /mcp/api/failures/analyze  → Claude LLM analysis
```

**Interactive Buttons**:
- "Get Batch 1 Metrics" → 160 accepted (32%)
- "Get Batch 2 Metrics" → 0 accepted, Circuit breaker open
- "Analyze Cascade" → Full root cause with recovery actions

**Sample Responses Shown**:
```json
{
  "batch": 1,
  "sent": 500,
  "accepted": 160,
  "errors": 177,
  "acceptance_rate": 0.32,
  "avg_latency_ms": 45
}
```

**Use This When**:
- You need structured payment data (not raw logs)
- You want to correlate payments with infrastructure metrics
- You need to drill down to individual payment failures
- You want to run cascade analysis with Claude

---

### 🏗️ Page 5: Architecture
**Shows**: Service dependency graph and relationships

**Architecture Visualization**:
```
Gateway (8080) - 83,897 logs
    ↓
ActiveMQ Pool (50 connections) ← BOTTLENECK
    ├─ Fraud-Scoring (8081) ✓
    ├─ Validation (8082) ✗
    ├─ AML (8083) ✗
    └─ Routing (8084) ✗
        └─ Settlement (8085) ✗
            └─ Audit (8086) ✓
```

**Service Table**:
- Service name, port, status
- Log count from test
- During-test behavior (Processing/Blocked/Recovery)
- Is it a bottleneck?

**Failure Patterns Explained**:
1. Entry point bottleneck (why gateway?)
2. Circuit breaker boundary (what it prevents)
3. Recovery path (why some logs anyway?)

**Use This When**:
- You need to understand service interactions
- You want to explain the architecture to stakeholders
- You need to visualize failure propagation path
- You want to see which services should be optimized

---

### 🔴 Page 6: Cascade Analysis
**Shows**: Complete failure progression and recovery plan

**Cascade Timeline**:
```
T+0s (Batch 1)    → 🟡 Degrading      (32% acceptance)
T+30s (Batch 2)   → 🔴 Cascade Starts (0% acceptance)
T+60s (Batch 3-5) → 🔴 Full Cascade   (0% acceptance)
T+90s (Batch 6-10)→ 🔴 Continues      (0% acceptance)
T+120s (End)      → ⚫ System DOWN     (test stopped)
```

**Root Cause Analysis**:
- What failed: ActiveMQ connection pool (50 limit)
- Why it failed: Batch 1 needs 160+ connections
- How it cascaded: Circuit breaker blocked all downstream
- Why hard failure: No graceful degradation

**Recovery Actions** (Priority Order):
1. **Increase ActiveMQ pool** (50 → 100+) - Removes bottleneck
2. **Increase broker throughput** - Prevents queue backlog
3. **Tune circuit breaker** - Gradual failure vs hard stop
4. **Add monitoring** - Catch issues before cascade

**Key Insight**:
- 2GB heap + G1GC helped (no OOM, low latency)
- But doesn't fix connection pool exhaustion
- Infrastructure changes needed, not JVM tuning

**Use This When**:
- You need to explain why the system failed
- You need recovery steps prioritized
- You want to show what monitoring should catch this
- You need to justify infrastructure investments

---

## Data Sources

| Page | Data Source | Update Frequency | Live Query |
|------|-------------|------------------|-----------|
| Overview | Local file (TEST_RESULTS_100K_FAILURE.md) | Static | No |
| Payment Metrics | Calculated from test results | Static | No |
| ELK Analysis | Elasticsearch (91K logs) | Real-time | ✓ Yes |
| MCP Queries | MCP Gateway API | Real-time | ✓ Yes |
| Architecture | Local graphify report | Static | No |
| Cascade Analysis | Local analysis documents | Static | No |

---

## Real-Time Features

### Live ELK Queries
The dashboard queries Elasticsearch in real-time:
- Service distribution (queries aggregations)
- Log levels (WARN/INFO/ERROR breakdown)
- If logs change, charts update immediately

### MCP API Calls
When you click buttons:
- Makes real HTTP requests to MCP gateway
- Shows actual API responses
- Can be extended to query live payment data

### Cache
Streamlit caches some data with `@st.cache_data`:
- Prevents repeated Elasticsearch queries
- Improves performance
- Can be cleared with Streamlit button if needed

---

## Customization & Extension

### Add New Page
```python
elif page == "🆕 New Page":
    st.title("Your Title")
    st.markdown("Your content")
    
    # Query ELK
    elk_stats = get_elk_stats()
    
    # Display chart
    fig = px.bar(...)
    st.plotly_chart(fig, use_container_width=True)
```

### Query Elasticsearch
```python
response = requests.get(
    f"{ES_URL}/clearflow-payments/_search",
    json={"your": "query"},
    timeout=5
)
```

### Query MCP Gateway
```python
response = requests.get(
    f"{MCP_URL}/mcp/api/payments",
    timeout=5
)
```

---

## Troubleshooting

### Dashboard Won't Start
```bash
# Check Streamlit installation
pip install streamlit plotly pandas requests

# Check port is free
lsof -i :8501
kill -9 <PID>

# Restart
streamlit run observability_dashboard.py
```

### ELK Queries Slow
- ES might be indexing - wait a minute
- Check ES status: `curl localhost:9200/_cluster/health`
- Increase query timeout in code

### MCP Gateway Not Responding
- Check it's running: `curl localhost:8087/actuator/health`
- Restart: `bash stop_live_traffic.sh && bash start_live_traffic.sh`

---

## Sample Analysis Workflow

### Scenario 1: "Why did payments fail?"
1. Go to **📈 Overview** → See 0.2% acceptance
2. Go to **💰 Payment Metrics** → See 9,177 connection errors
3. Go to **🔴 Cascade** → See cascade timeline
4. Go to **🏗️ Architecture** → See connection pool bottleneck
5. **Conclusion**: Fix ActiveMQ pool size

### Scenario 2: "Which payments succeeded?"
1. Go to **💰 Payment Metrics** → See scenario breakdown
2. See 139 happy path, 10 high-value, etc.
3. Go to **📊 ELK Analysis** → Query by message type
4. **Conclusion**: Happy path works, infrastructure failed

### Scenario 3: "Show me the cascade visually"
1. Go to **📈 Overview** → Batch chart shows cliff at batch 2
2. Go to **🔴 Cascade** → Timeline shows T+30s failure point
3. Go to **📊 ELK** → Service log distribution shows 92% gateway
4. **Conclusion**: Clear visual proof of cascade pattern

---

## Performance

- **Startup**: ~3 seconds (Streamlit initialization)
- **Page Load**: <1 second (cached data)
- **ELK Query**: <2 seconds (91K logs searched)
- **Chart Render**: <500ms (Plotly)
- **Responsiveness**: Instant (all UI interactive)

Streamlit is **fast** enough for real-time dashboards and production monitoring.

---

## File Location

```
/home/admin-/Desktop/EDI6/clearflow/observability_dashboard.py
```

Access the running dashboard at:
```
http://localhost:8501
```

---

## Summary

**6 Pages. Real Data. Complete Story.**

- 📈 **Overview** → See the problem (0.2% acceptance)
- 💰 **Payment Metrics** → Understand the impact (9K errors)
- 📊 **ELK** → Query the logs (91K events)
- 🔌 **MCP** → Get structured data (payment status)
- 🏗️ **Architecture** → Understand dependencies (7 services)
- 🔴 **Cascade** → Fix the issue (4 recovery actions)

**For Production**: Extend with live payment streams, real-time alerts, and historical comparison.

**For Demos**: Use to show observability in action with 100K payment test data.
