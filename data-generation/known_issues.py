#!/usr/bin/env python3
"""Curated list of confirmed, real, recurring noise -- errors that are true
(really happening in the logs) but NOT related to whatever incident is being
investigated. The real on-call-runbook pattern: don't make every
investigation rediscover the same red herring from scratch.

Every entry here was found live, misleading a real investigation, verified
to be unrelated to the fault it appeared near. Add to this list only after
confirming a pattern is a genuine recurring distractor, not a one-off.
"""

KNOWN_ISSUES = [
    {
        "id": "clickhouse-httpclient5-missing",
        "service": "settlement",
        "signature": "ClickHouseAnalyticsService / NoClassDefFoundError / Connection refused writing to ClickHouse",
        "confirmed_unrelated_to": ["AML_HOLD", "CASSANDRA_OUTAGE", "MONGODB_OUTAGE", "AML_SERVICE_DEGRADATION_RETRY_CASCADE"],
        "explanation": (
            "settlement's ClickHouseAnalyticsService is missing the httpclient5 dependency (or "
            "ClickHouse itself isn't reachable), so it repeatedly fails to write analytics events. "
            "This is a REAL bug, but it is a persistent background issue independent of whatever "
            "incident is being investigated -- confirmed live 2026-09-09/10, misled two separate "
            "agentic investigations into wrongly blaming settlement. If this is the ONLY evidence "
            "pointing at settlement, treat it as noise and keep looking; it doesn't stall the payment "
            "pipeline (settlement's actual payment-processing logic doesn't depend on ClickHouse)."
        ),
    },
]


def get_known_issues():
    return {"known_issues": KNOWN_ISSUES}


if __name__ == "__main__":
    import json
    print(json.dumps(get_known_issues(), indent=2))
