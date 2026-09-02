#!/usr/bin/env python3
"""
ClearFlow Cascading Failure Analyzer

Uses:
1. Graphify architecture graph (service dependencies)
2. Test logs (actual failures)
3. Claude LLM (correlation analysis)

Analyzes how a failure in one service cascades through the system.
"""
import json
import subprocess
import sys
from datetime import datetime

try:
    import requests
    from anthropic import Anthropic
except ImportError:
    print("pip install requests anthropic")
    sys.exit(1)

GRAPHIFY_GRAPH = "/home/admin-/Desktop/EDI6/clearflow/graphify-out/GRAPH_REPORT.md"
LOG_DIR = "/home/admin-/Desktop/EDI6/clearflow/dev-logs"
MCP_GATEWAY = "http://localhost:8087"

# Service dependency map from graphify
SERVICES = {
    "gateway": {
        "port": 8080,
        "depends_on": ["fraud-scoring", "validation-enrichment", "aml-compliance"],
        "messaging": ["ActiveMQ", "Kafka", "Solace"],
        "next_stage": "fraud-scoring"
    },
    "fraud-scoring": {
        "port": 8081,
        "depends_on": ["validation-enrichment"],
        "messaging": ["Kafka"],
        "next_stage": "validation-enrichment"
    },
    "validation-enrichment": {
        "port": 8082,
        "depends_on": ["aml-compliance"],
        "messaging": ["Kafka"],
        "next_stage": "aml-compliance"
    },
    "aml-compliance": {
        "port": 8083,
        "depends_on": ["routing-execution"],
        "messaging": ["Kafka"],
        "next_stage": "routing-execution"
    },
    "routing-execution": {
        "port": 8084,
        "depends_on": ["settlement"],
        "messaging": ["Kafka", "ActiveMQ"],
        "next_stage": "settlement"
    },
    "settlement": {
        "port": 8085,
        "depends_on": ["audit"],
        "messaging": ["Kafka"],
        "next_stage": "audit"
    },
    "audit": {
        "port": 8086,
        "depends_on": [],
        "messaging": ["Kafka", "Cassandra"],
        "next_stage": None
    }
}

def read_graphify():
    """Read architecture graph from graphify report"""
    try:
        with open(GRAPHIFY_GRAPH) as f:
            return f.read()
    except:
        return None

def get_test_logs():
    """Collect logs from all services"""
    logs = {}
    try:
        for service in SERVICES.keys():
            log_file = f"{LOG_DIR}/{service}.log"
            try:
                with open(log_file) as f:
                    content = f.read()
                    if content:
                        logs[service] = content[-5000:]  # Last 5KB
            except:
                pass
    except:
        pass
    return logs

def analyze_cascade(failure_service, test_logs):
    """Use Claude to analyze cascading failures"""
    import os
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("    ⚠️  ANTHROPIC_API_KEY not set. Set it via: export ANTHROPIC_API_KEY=sk-...")
        return {"error": "API key not set"}
    client = Anthropic(api_key=api_key)

    # Build the context
    graph = read_graphify()

    cascade_prompt = f"""You are analyzing a payment system cascading failure.

## System Architecture (from graphify)
{graph}

## Service Dependencies
{json.dumps(SERVICES, indent=2)}

## Test Logs (last 5KB from each service)
{json.dumps(test_logs, indent=2)}

## Failure Scenario
The test crashed at batch 10/200 (5,000 payments processed).

### Questions to Answer:
1. **Primary failure**: Which service failed first?
2. **Root cause**: What caused it? (memory, queue full, timeout, etc.)
3. **Cascade**: How did it propagate to other services?
4. **Timeline**: When did each service fail after the primary failure?
5. **Evidence**: Which log lines prove this?

### Format your response as JSON:
{{
  "primary_failure_service": "service_name",
  "root_cause": "description",
  "root_cause_evidence": ["log line 1", "log line 2"],
  "cascade_sequence": [
    {{"service": "A", "failed_at_ms": 1000, "reason": "upstream timeout"}},
    {{"service": "B", "failed_at_ms": 2500, "reason": "queue overflow"}},
    {{"service": "C", "failed_at_ms": 3100, "reason": "circuit breaker open"}}
  ],
  "affected_services": ["list"],
  "recovery_action": "what to do to fix",
  "monitoring_gaps": ["what we should be alerting on"],
  "confidence": 0.85
}}"""

    print("\n🔍 Analyzing cascading failure...\n")

    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=2000,
        messages=[
            {
                "role": "user",
                "content": cascade_prompt
            }
        ]
    )

    try:
        import re
        content = response.content[0].text
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except:
        pass

    return {"analysis": response.content[0].text}

def main():
    print("=" * 70)
    print("  ClearFlow Cascading Failure Analyzer")
    print("=" * 70)

    # Get test logs
    print("\n[1] Collecting logs from all services...")
    test_logs = get_test_logs()
    print(f"    Collected logs from {len(test_logs)} services")

    if not test_logs:
        print("    ✗ No logs found. Run tests first.")
        return

    # Analyze cascade
    print("\n[2] Analyzing cascade with Claude...")
    analysis = analyze_cascade("gateway", test_logs)

    # Display results
    print("\n" + "=" * 70)
    print("  ANALYSIS RESULTS")
    print("=" * 70)

    if "primary_failure_service" in analysis:
        print(f"\n📍 Primary Failure: {analysis['primary_failure_service']}")
        print(f"🎯 Root Cause: {analysis['root_cause']}")
        print(f"   Confidence: {analysis.get('confidence', 0):.0%}")

        if "root_cause_evidence" in analysis:
            print(f"\n📄 Evidence:")
            for line in analysis.get("root_cause_evidence", [])[:3]:
                print(f"   • {line[:100]}")

        if "cascade_sequence" in analysis:
            print(f"\n🔗 Cascade Sequence:")
            for i, event in enumerate(analysis["cascade_sequence"], 1):
                print(f"   {i}. {event['service']:<20} @ {event.get('failed_at_ms', '?')}ms: {event['reason']}")

        if "recovery_action" in analysis:
            print(f"\n💡 Recovery Action: {analysis['recovery_action']}")

        if "monitoring_gaps" in analysis:
            print(f"\n⚠️  Monitoring Gaps (add alerts):")
            for gap in analysis.get("monitoring_gaps", [])[:3]:
                print(f"   • {gap}")
    else:
        print(json.dumps(analysis, indent=2))

    print("\n" + "=" * 70)

if __name__ == "__main__":
    main()
