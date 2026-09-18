#!/usr/bin/env python3
"""Real distributed-trace reconstruction: pull every log line across ALL
services for one correlationId, sorted by time, into a single causal
timeline -- the way Jaeger would show one request's journey, instead of
searching one service's logs at a time and manually stitching the story
together.

Verified live 2026-09-10: correlationId coverage is real but uneven --
fraud-scoring/validation-enrichment/aml-compliance/routing-execution are
>98% populated, gateway is <1% (rarely sets it before handoff), settlement
~27%, audit ~50%. A trace built from this will often start mid-pipeline,
not at gateway -- that's a real property of the data, disclosed here, not
a bug in this tool.
"""
import requests

ES = "http://elastic:changeme@localhost:9200"


def get_correlation_trace(correlation_id, limit=200):
    resp = requests.get(f"{ES}/clearflow-*/_search", timeout=15, json={
        "size": limit,
        "query": {"term": {"correlationId": correlation_id}},
        "sort": [{"@timestamp": "asc"}],
        "_source": ["@timestamp", "service", "eventType", "level", "message", "paymentId"],
    })
    hits = resp.json().get("hits", {}).get("hits", [])
    if not hits:
        return {"result": f"No events found for correlationId={correlation_id}. "
                           "Coverage is uneven (gateway rarely sets it) -- try a different payment/event."}
    trace = [f"[{h['_source'].get('@timestamp')}] [{h['_source'].get('service')}] "
             f"{(h['_source'].get('eventType') or '')} {h['_source'].get('message','')[:150]}"
             for h in hits]
    services_seen = sorted(set(h["_source"].get("service") for h in hits))
    return {"correlation_id": correlation_id, "n_events": len(hits),
            "services_in_trace": services_seen, "trace": trace}


def get_correlation_id_for_payment(payment_id):
    """Look up a correlationId from a known paymentId, since the agent usually
    has payment IDs, not correlation IDs, from other evidence."""
    resp = requests.get(f"{ES}/clearflow-*/_search", timeout=15, json={
        "size": 1,
        "query": {"bool": {"filter": [{"term": {"paymentId": payment_id}},
                                       {"exists": {"field": "correlationId"}}]}},
        "sort": [{"@timestamp": "asc"}],
        "_source": ["correlationId"],
    })
    hits = resp.json().get("hits", {}).get("hits", [])
    if not hits:
        return None
    return hits[0]["_source"].get("correlationId")


if __name__ == "__main__":
    import sys
    import json
    if len(sys.argv) > 1:
        print(json.dumps(get_correlation_trace(sys.argv[1]), indent=2))
