#!/usr/bin/env python3
"""recall_similar_incidents_v2 -- fixes a real, confirmed precision bug in
agent_memory.recall_similar_incidents.

Diagnosed, not assumed: querying "ClickHouse connection refused settlement"
against the real memory store returns only REDIS_OUTAGE / MONGODB_OUTAGE
cases -- zero Cassandra/settlement-related hits -- even though a case with
real Cassandra evidence (LIVE-1a1dcc24, SETTLEMENT_DB_FAILURE_LIQUIDITY_CASCADE)
is right there and matches "clickhouse" cleanly on its own. The cause: v1
OR-joins all query tokens with equal weight, and "settlement" alone matches
57 of ~150 stored cases (it's a service name, near-ubiquitous) while
"clickhouse" matches only 10 -- the common term's sheer match volume
dominates bm25 ranking over the actually distinctive one.

Fix: rank candidate tokens by real document frequency in cases_fts (query
each token's own match count first), then build the FTS query from the
RAREST tokens first (AND-style, via FTS5's implicit-AND space syntax) so
distinctive evidence terms drive the match, falling back to the full
OR-all-tokens query only if the selective one returns nothing. Every call
logs which tokens were chosen and their document frequencies.
"""
import json
import os
import sqlite3
import time

from agent_memory import connect

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_memory_recall_v2_log.jsonl")

MAX_SELECTIVE_TOKENS = 5  # how many of the rarest tokens to AND together in the first pass


def _log(record):
    record["ts"] = time.time()
    try:
        with open(LOG_PATH, "a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass


def _token_doc_freq(conn, token):
    try:
        return conn.execute("SELECT count(*) FROM cases_fts WHERE cases_fts MATCH ?", (token,)).fetchone()[0]
    except sqlite3.OperationalError:
        return 10**6  # a token FTS5 can't parse as a query term (rare) sorts last, not first


def _run_query(conn, fts_query, exclude_incident_id, limit):
    return conn.execute(
        "SELECT c.incident_id, c.fault_type, c.root_service, c.predicted, c.hit, c.source, "
        "snippet(cases_fts, 2, '[', ']', '...', 20), bm25(cases_fts) "
        "FROM cases_fts JOIN cases c ON c.id = cases_fts.rowid "
        "WHERE cases_fts MATCH ? AND c.incident_id != ? ORDER BY rank LIMIT ?",
        (fts_query, exclude_incident_id or "", limit),
    ).fetchall()


def recall_similar_incidents_v2(query_text, limit=5, exclude_incident_id=None):
    conn = connect()
    tokens = [t for t in "".join(c if c.isalnum() else " " for c in query_text).split() if len(t) > 3]
    if not tokens:
        conn.close()
        _log({"query": query_text[:100], "tokens": 0, "result": "no usable terms"})
        return {"result": "no usable search terms"}

    doc_freq = {t: _token_doc_freq(conn, t) for t in set(tokens[:12])}
    ranked_tokens = sorted(set(tokens[:12]), key=lambda t: doc_freq[t])
    selective_tokens = ranked_tokens[:MAX_SELECTIVE_TOKENS]

    strategy = "selective-AND"
    rows = _run_query(conn, " ".join(selective_tokens), exclude_incident_id, limit)  # bare space = FTS5 implicit AND
    if not rows:
        strategy = "fallback-OR-all"
        rows = _run_query(conn, " OR ".join(tokens[:12]), exclude_incident_id, limit)
    conn.close()

    if not rows:
        _log({"query": query_text[:100], "tokens": len(tokens), "doc_freq": doc_freq, "result": "miss"})
        return {"result": f"No similar past incidents found for: {query_text[:100]}"}

    _log({
        "query": query_text[:100], "strategy": strategy,
        "selective_tokens": selective_tokens, "doc_freq": doc_freq,
        "bm25_scores": [round(r[7], 2) for r in rows],
        "n_results": len(rows), "result": "hit",
    })
    return {"similar_past_incidents": [
        {"incident_id": r[0], "fault_type": r[1], "confirmed_root_cause": r[2],
         "past_prediction": r[3], "past_prediction_was_correct": bool(r[4]) if r[4] is not None else None,
         "source": r[5], "matching_evidence_snippet": r[6]}
        for r in rows
    ], "retrieval_strategy": strategy}


if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "ClickHouse connection refused settlement"
    print(json.dumps(recall_similar_incidents_v2(q), indent=2))
