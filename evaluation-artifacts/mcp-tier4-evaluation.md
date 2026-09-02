# ClearFlow Tier 4 — MCP Tool Evaluation Results

**Test Date**: 2026-05-21  
**MCP Gateway**: http://localhost:8087 (UP)  
**Testing Approach**: Query real payment data from 100K test

## Tool 1: getPaymentTimeline

**Purpose**: Reconstruct full event timeline for a payment  
**Expected**: 7 events (gateway → fraud → validation → AML → routing → settlement → audit)

### Test Result

```
Tool: getPaymentTimeline
Status: READY TO INVOKE
Endpoint: /mcp/api/getPaymentTimeline
Input: paymentId (UUID)
Output: Ordered event timeline with timestamps and service names
Evaluation: [To be executed when MCP HTTP endpoints available]
```

## Tool 2: classifyRootCause

**Purpose**: ML-powered failure classification  
**Expected**: FRAUD_BLOCK, AML_HIT, TIMEOUT, LIQUIDITY_EXHAUSTED, etc.

### Test Result

```
Tool: classifyRootCause
Status: READY TO INVOKE
Endpoint: /mcp/api/classifyRootCause
Input: Payment timeline or error logs
Output: Failure category + confidence score
Evaluation: [To be executed against 100 failed payments]
```

## Tool 3: explainIncidentWithCode

**Purpose**: LLM-powered root cause analysis with code references  
**Expected**: Java class names, methods, actual system behavior explanation

### Test Result

```
Tool: explainIncidentWithCode
Status: READY TO INVOKE
Endpoint: /mcp/api/explainIncidentWithCode
Input: Timeline + code graph context
Output: Human-readable RCA with Java citations
Evaluation: [To be executed against sample routing failures]
```

## Evaluation Framework

### Metrics to Measure

| Tool | Metric | Target | Method |
|------|--------|--------|--------|
| getPaymentTimeline | Reconstruction Accuracy | 100% | Verify all 7 events present and ordered |
| classifyRootCause | Classifier F₁ Score | > 0.8 | Compare predictions vs ground truth |
| classifyRootCause | Cohen's κ | > 0.7 | Measure inter-rater reliability |
| explainIncidentWithCode | Citation Accuracy | > 95% | Verify class/method names exist in codebase |
| explainIncidentWithCode | Fact Accuracy | > 90% | Validate claims against source code |
| explainIncidentWithCode | Hallucination Rate | < 5% | Count invented details |

### Test Data Available

From 100K test:
- ✅ 95,000 accepted payments (baseline)
- ✅ 5,000 AML rejections (known failures)
- ✅ 91K+ structured logs with correlationId
- ✅ 1,162-node code graph for validation

### Why Not Yet Executed

MCP endpoint access via HTTP is constrained. Options:
1. **Query Elasticsearch directly** (alternative): Parse timeline from logs
2. **Use MCP SSE protocol** (proper): Connect via proper MCP client
3. **Call Java methods directly** (dev): Spring Boot actuator endpoints

**Current Status**: Framework + test data ready. Endpoint integration TBD.

## Summary

- [x] MCP gateway running (health check PASS)
- [x] Test data collected (100K payment logs)
- [x] Evaluation framework designed
- [x] Sample payments identified
- [ ] HTTP endpoint access (needs research)
- [ ] Tool invocation (blocked on endpoint)
- [ ] Metrics collection (ready to execute)

**Recommendation**: Use Elasticsearch direct query to reconstruct timelines (equivalent to getPaymentTimeline). Execute classifier evaluation on 100 labeled failures. Manual LLM validation on 5 routing failures.

