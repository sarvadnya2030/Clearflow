# ClearFlow Real-Time Observability: ELK + MCP + Graphify Demo

## 1. Elasticsearch Log Analysis (ELK Stack)

### Query 1: Service Error Breakdown
```bash
curl -s -X GET "localhost:9200/clearflow-payments/_search" -H "Content-Type: application/json" -d '{
  "aggs": {
    "errors_by_service": {
      "terms": {"field": "SERVICE_NAME", "size": 10},
      "aggs": {
        "error_count": {
          "filter": {"term": {"level": "ERROR"}}
        }
      }
    }
  },
  "size": 0
}'
```

### Query 2: Cascade Timeline by Timestamp
```bash
curl -s -X GET "localhost:9200/clearflow-payments/_search" -H "Content-Type: application/json" -d '{
  "aggs": {
    "timeline": {
      "date_histogram": {
        "field": "@timestamp",
        "fixed_interval": "1m"
      },
      "aggs": {
        "services": {"terms": {"field": "SERVICE_NAME"}}
      }
    }
  },
  "size": 0
}'
```

### Query 3: Find Connection Pool Exhaustion Events
```bash
curl -s -X GET "localhost:9200/clearflow-payments/_search" -H "Content-Type: application/json" -d '{
  "query": {
    "bool": {
      "must": [
        {"match": {"message": "connection"}},
        {"terms": {"level": ["ERROR", "WARN"]}}
      ]
    }
  },
  "size": 100,
  "sort": [{"@timestamp": {"order": "asc"}}]
}'
```

---

## 2. MCP Gateway Payment Queries

### Query Payment Status by ID
```bash
curl -s "http://localhost:8087/mcp/api/payments/{paymentId}/status" \
  -H "Authorization: Bearer token"
```

### Query Cascading Failure Pattern
```bash
curl -s "http://localhost:8087/mcp/api/failures/cascade" \
  -H "Authorization: Bearer token" \
  -d '{"start_time":"2026-04-25T13:01:00Z", "end_time":"2026-04-25T13:15:00Z"}'
```

---

## 3. Graphify Architecture Analysis with Real Data

The `graphify-out/GRAPH_REPORT.md` shows:
```
gateway (8080) [83,897 logs]
  ├─> fraud-scoring (8081) [3,541 logs]
  ├─> validation-enrichment (8082) [26 logs]
  ├─> aml-compliance (8083) [82 logs]
  └─> routing-execution (8084) [26 logs]
      └─> settlement (8085) [60 logs]
          └─> audit (8086) [3,514 logs]
```

**Insight**: Gateway is the bottleneck - 83K logs vs 26 in validation-enrichment shows cascade pattern visually.

---

## 4. Real Data Summary

**Indexed in Elasticsearch**: 91,146 logs
- Gateway: 83,897 (92% of traffic)
- Audit: 3,514 
- Fraud-scoring: 3,541
- Others: ~194

**Timeline**: 2026-04-25 13:01 - 13:48 (47 minutes)

**Cascade Visible In Logs**:
- 13:01 - Services startup
- 13:02:04 - Gateway "Started" message
- 13:48:54 - Final log entry (gateway shutdown)

**Failure Signature**:
- Batch 1 (13:XX) - Mixed success/error  
- Batch 2+ (13:XX) - 100% errors logged
- Connection refused pattern spreads downstream

---

## 5. Combined Observability Workflow

1. **See failure in ELK**: Query by timestamp shows cascade progression
2. **Correlate with payment IDs**: Find which batches failed
3. **Query MCP for details**: Get structured payment status
4. **Visualize with graphify**: See which service failed first
5. **Identify root cause**: Connection pool → circuit breaker → cascade

---

## Log Locations

```
Elasticsearch: http://localhost:9200/clearflow-payments
Index size: 91,146 documents
Service logs: /home/admin-/Desktop/EDI6/clearflow/dev-logs/
Graphify report: /home/admin-/Desktop/EDI6/clearflow/graphify-out/GRAPH_REPORT.md
```

---

## Next Steps

1. Set up Kibana dashboards for real-time visualization
2. Create alerts based on error rate by service
3. Use MCP gateway to drill down into individual payment failures
4. Correlate ELK logs with payment statuses for root cause analysis
5. Integrate graphify insights into Kibana for dependency visualization

This demonstrates how ELK captures the volume, MCP provides structured queries, and graphify shows the architecture impact - together they enable complete observability of the cascading failure pattern.
