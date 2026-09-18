#!/usr/bin/env python3
"""search_live_elasticsearch_v2 -- fixes a real bug in agentic_hardcases.search_live_es:
that function sorts @timestamp DESC (most-recent-first) and caps at 15 results, which
means in a cascading failure the EARLIEST error (usually the real trigger) can get
buried under later downstream noise and never make it into the 15 shown.

A second function in the same codebase, eval_harness._fetch_sample_logs_for_agentic
(builds the base evidence sample every agent starts from), already sorts ASC
specifically to avoid this -- its own comment explains why. The live-ES tool, which
the prompt tells the agent is the MORE authoritative source, had the worse convention.

Fix: fetch both ends of the window -- the earliest K events (catches the trigger)
and the latest K (catches current state / recovery), deduplicated, rather than one
arbitrary 15-result window sorted the wrong way.

Every call is logged (service, keyword, level filter applied, counts from each half,
overlap) so the change can be measured, not assumed.
"""
import json
import os
import time

import requests

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "search_live_es_v2_log.jsonl")


def _log(record):
    record["ts"] = time.time()
    try:
        with open(LOG_PATH, "a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass


def _query(start, end, service, keyword, sort_dir, size):
    filters = [
        {"range": {"@timestamp": {"gte": start.isoformat(), "lte": end.isoformat()}}},
        {"term": {"service": service}},
    ]
    must = []
    if keyword:
        must.append({"match_phrase": {"message": keyword}})
    else:
        filters.append({"terms": {"level": ["ERROR", "WARN"]}})
    body = {"size": size, "query": {"bool": {"filter": filters, "must": must}},
            "sort": [{"@timestamp": sort_dir}], "_source": ["message", "level", "@timestamp"]}
    r = requests.post("http://localhost:9200/clearflow-*/_search", json=body, timeout=10)
    r.raise_for_status()
    return r.json().get("hits", {}).get("hits", [])


def search_live_es_v2(start, end, service, keyword=None, half_size=10):
    """Same filters as v1 (service, optional keyword, ERROR/WARN-only when no
    keyword), but returns the earliest half_size events AND the latest
    half_size events in the window, not one arbitrary 15 sorted the wrong way.
    """
    try:
        earliest = _query(start, end, service, keyword, "asc", half_size)
        latest = _query(start, end, service, keyword, "desc", half_size)
    except Exception as e:
        _log({"service": service, "keyword": keyword, "error": str(e)})
        return {"error": str(e)}

    if not earliest and not latest:
        _log({"service": service, "keyword": keyword, "result": "miss"})
        return {"result": f"No matching logs found for {service}" +
                           (f" containing '{keyword}'" if keyword else "") + " in this window."}

    # dedupe by (timestamp, message) in case the window is small enough that both
    # halves overlap -- earliest-half entries win the ordering, latest-half entries
    # append only what's not already shown
    seen = set()
    ordered = []
    for h in earliest:
        key = (h["_source"].get("@timestamp"), h["_source"].get("message"))
        if key not in seen:
            seen.add(key)
            ordered.append(("earliest", h))
    tail = []
    for h in latest:
        key = (h["_source"].get("@timestamp"), h["_source"].get("message"))
        if key not in seen:
            seen.add(key)
            tail.append(("latest", h))
    # latest-half results come back newest-first; reverse so the whole combined
    # list still reads chronologically (earliest block, then a marker, then the
    # tail in time order) instead of latest-first within its own block
    tail.reverse()

    logs = [f"[{h['_source'].get('@timestamp','')}] [{h['_source'].get('level','')}] {h['_source'].get('message','')}"
            for _, h in ordered]
    if tail:
        logs.append("--- (gap: window continues) ---" if len(ordered) + len(tail) < len(earliest) + len(latest)
                     else "--- (most recent in window) ---")
        logs.extend(f"[{h['_source'].get('@timestamp','')}] [{h['_source'].get('level','')}] {h['_source'].get('message','')}"
                    for _, h in tail)

    _log({
        "service": service, "keyword": keyword,
        "earliest_count": len(earliest), "latest_count": len(latest),
        "overlap": len(earliest) + len(latest) - len(ordered) - len(tail),
        "total_returned": len(ordered) + len(tail),
        "result": "hit",
    })
    return {"logs": logs}


if __name__ == "__main__":
    import sys
    from datetime import datetime, timedelta, timezone
    service = sys.argv[1] if len(sys.argv) > 1 else "settlement"
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=1)
    print(json.dumps(search_live_es_v2(start, end, service), indent=2)[:2000])
