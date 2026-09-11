#!/usr/bin/env python3
"""Real episodic memory for the agentic RCA loop -- SQLite (single file,
survives crashes, nothing extra to keep running), not the Neo4j graph that
sat dead for 4 days unnoticed. Two purposes:

1. Seeded once from every confirmed gold case's real reasoning/evidence
   (currently 97+), so the agent can recall "have I seen this exact log
   signature before, and what was the confirmed answer" instead of
   rediscovering the same pattern from zero on every investigation --
   genuine case-based learning, the RCAEval/MicroRCA-Agent "episodic
   memory" pattern applied to this project's own growing case corpus.
2. Grows with every agentic investigation this project runs from now on
   (record_investigation), so it compounds over time rather than staying
   static.

Uses SQLite FTS5 for real full-text search over reasoning traces and
evidence quotes -- not a hand-rolled keyword scan.
"""
import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "agent_memory.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS strategies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fault_type TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    content TEXT NOT NULL,
    n_cases_used INTEGER NOT NULL,
    n_hits INTEGER,
    n_misses INTEGER,
    distilled_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT NOT NULL,
    fault_type TEXT,
    root_service TEXT NOT NULL,
    predicted TEXT,
    hit INTEGER,
    source TEXT NOT NULL,          -- 'gold_case' or 'agentic_investigation'
    evidence_text TEXT NOT NULL,   -- reasoning trace / evidence quote / final answer text
    recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(incident_id, source)
);
CREATE VIRTUAL TABLE IF NOT EXISTS cases_fts USING fts5(
    incident_id UNINDEXED, fault_type, evidence_text, content='cases', content_rowid='id'
);
CREATE TRIGGER IF NOT EXISTS cases_ai AFTER INSERT ON cases BEGIN
    INSERT INTO cases_fts(rowid, incident_id, fault_type, evidence_text)
    VALUES (new.id, new.incident_id, new.fault_type, new.evidence_text);
END;
"""


def connect(db_path=DB_PATH):
    conn = sqlite3.connect(db_path, timeout=30)
    conn.executescript(SCHEMA)
    return conn


def already_recorded(conn, incident_id, source):
    # Real bug fixed: this used to key on incident_id ALONE, so once every gold case was
    # seeded (source='gold_case'), an agentic investigation's own record_investigation call
    # for that same incident_id silently no-op'd -- confirmed live: after 28 cases run in the
    # full-benchmark pass, only 1 of 28 agentic_investigation rows had actually been written
    # (the one gold case that happened to fail seeding). Memory wasn't compounding at all.
    row = conn.execute("SELECT 1 FROM cases WHERE incident_id = ? AND source = ?",
                        (incident_id, source)).fetchone()
    return row is not None


def record_case(conn, incident_id, fault_type, root_service, predicted, hit, source, evidence_text):
    if already_recorded(conn, incident_id, source):
        return False
    conn.execute(
        "INSERT INTO cases (incident_id, fault_type, root_service, predicted, hit, source, evidence_text) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (incident_id, fault_type, root_service, predicted, int(bool(hit)) if hit is not None else None,
         source, evidence_text),
    )
    conn.commit()
    return True


def record_investigation(incident_id, fault_type, root_service, predicted, hit, final_text):
    conn = connect()
    record_case(conn, incident_id, fault_type, root_service, predicted, hit,
                "agentic_investigation", final_text)
    conn.close()


def recall_similar_incidents(query_text, limit=5, exclude_incident_id=None):
    """Real FTS5 search over past reasoning/evidence text -- what an agent
    should call to check 'have I seen this pattern before.'

    exclude_incident_id is NOT optional in practice -- when evaluating the
    agent against a gold case that's ALSO seeded into this memory (every
    gold case is, since seed_from_gold_cases loads all of them), omitting
    it lets the agent look up its own answer key instead of reasoning.
    Found live: LIVE-125bb06d, one of the 11 hard test cases, came back as
    its own top match on a query built from its own evidence. Every caller
    in this project's evaluation harnesses MUST pass the current incident's
    own id here."""
    conn = connect()
    # FTS5 query syntax breaks on raw punctuation from log lines -- keep only
    # alphanumeric tokens, which is what actually carries signal anyway.
    tokens = [t for t in "".join(c if c.isalnum() else " " for c in query_text).split() if len(t) > 2]
    if not tokens:
        conn.close()
        return {"result": "no usable search terms"}
    fts_query = " OR ".join(tokens[:12])
    rows = conn.execute(
        "SELECT c.incident_id, c.fault_type, c.root_service, c.predicted, c.hit, c.source, "
        "snippet(cases_fts, 2, '[', ']', '...', 20) "
        "FROM cases_fts JOIN cases c ON c.id = cases_fts.rowid "
        "WHERE cases_fts MATCH ? AND c.incident_id != ? ORDER BY rank LIMIT ?",
        (fts_query, exclude_incident_id or "", limit),
    ).fetchall()
    conn.close()
    if not rows:
        return {"result": f"No similar past incidents found for: {query_text[:100]}"}
    return {"similar_past_incidents": [
        {"incident_id": r[0], "fault_type": r[1], "confirmed_root_cause": r[2],
         "past_prediction": r[3], "past_prediction_was_correct": bool(r[4]) if r[4] is not None else None,
         "source": r[5], "matching_evidence_snippet": r[6]}
        for r in rows
    ]}


def seed_from_gold_cases(gold_dir="gold_cases", manifest_path="gold_cases_manifest.csv"):
    """One-time (idempotent) seed from every confirmed gold case's real
    evidence -- the reasoning trace IS the thing worth remembering, not the
    raw event dump."""
    import csv
    conn = connect()
    n_added = 0
    with open(manifest_path) as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        if row["confirmed"] != "true":
            continue
        incident_id = row["incident_id"]
        path = Path(gold_dir) / f"{incident_id}.json"
        if not path.exists():
            continue
        gold = json.loads(path.read_text())
        evidence_text = (gold.get("reasoning_trace") or "") + " | " + " | ".join(gold.get("evidence_reviewed") or [])
        if not evidence_text.strip(" |"):
            continue
        added = record_case(conn, incident_id, row["fault_type"], row["root_service"],
                             predicted=None, hit=None, source="gold_case", evidence_text=evidence_text)
        n_added += added
    conn.close()
    return n_added


def distill_strategy(fault_type, client=None, model=None):
    """Tier 3, ReasoningBank-style: turn the raw case log for one fault_type into
    ONE reusable strategy (title/description/content), extracted from BOTH hits
    and misses -- a miss teaches "don't do X" just as much as a hit teaches "do Y".
    Idempotent per fault_type (UNIQUE constraint, re-distilling replaces the old
    strategy with a fresher one as more cases accumulate)."""
    conn = connect()
    rows = conn.execute(
        "SELECT incident_id, root_service, predicted, hit, source, evidence_text "
        "FROM cases WHERE fault_type = ? ORDER BY recorded_at", (fault_type,)
    ).fetchall()
    if len(rows) < 2:
        conn.close()
        return None  # not enough cases yet to generalize from

    n_hits = sum(1 for r in rows if r[3] == 1)
    n_misses = sum(1 for r in rows if r[3] == 0)
    case_lines = []
    for incident_id, root_service, predicted, hit, source, evidence_text in rows:
        outcome = ("CONFIRMED (gold)" if source == "gold_case" else
                   "AGENT GOT THIS RIGHT" if hit == 1 else
                   "AGENT GOT THIS WRONG (predicted %s, actually %s)" % (predicted, root_service) if hit == 0
                   else "unresolved")
        case_lines.append(f"- [{outcome}] confirmed root cause = {root_service}. "
                           f"Evidence: {evidence_text[:400]}")
    cases_block = "\n".join(case_lines[:30])  # cap for prompt size

    prompt = f"""You are distilling {len(rows)} real, confirmed incidents of fault type {fault_type} into ONE
reusable investigative strategy for an RCA agent that will face this fault type again. Some entries are
agent mistakes -- these are as valuable as the successes, since they show a specific wrong pattern to avoid.

{cases_block}

Extract ONE strategy others in your position can reuse. Be SPECIFIC to this fault type -- name the exact
log event types, keywords, or signal patterns that were decisive across these cases, and specific wrong
turns to avoid if any agent mistakes are shown above.

Respond with ONLY this JSON:
{{"title": "<5-8 word strategy name>", "description": "<one sentence>",
  "content": "<3-5 sentences: what to check first, what decisive signal to search for, what mistake to avoid>"}}"""

    if client is None:
        import eval_harness as eh
        client = eh._get_llm_client()
        model = eh.NVIDIA_MODEL
    resp = client.chat.completions.create(
        model=model, messages=[{"role": "user", "content": prompt}],
        temperature=0, max_tokens=600,
    )
    text = resp.choices[0].message.content or ""
    if "```" in text:
        text = text.split("```")[1].replace("json", "", 1) if text.count("```") >= 2 else text
    try:
        parsed = json.loads(text[text.find("{"):text.rfind("}") + 1])
    except (json.JSONDecodeError, ValueError):
        conn.close()
        return None

    conn.execute(
        "INSERT INTO strategies (fault_type, title, description, content, n_cases_used, n_hits, n_misses) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(fault_type) DO UPDATE SET title=excluded.title, description=excluded.description, "
        "content=excluded.content, n_cases_used=excluded.n_cases_used, n_hits=excluded.n_hits, "
        "n_misses=excluded.n_misses, distilled_at=datetime('now')",
        (fault_type, parsed["title"], parsed["description"], parsed["content"], len(rows), n_hits, n_misses),
    )
    conn.commit()
    conn.close()
    return parsed


def get_learned_strategy(fault_type):
    """What the agent should read BEFORE investigating -- upfront prompt injection,
    not a tool call the model might skip (the lesson from every other mandatory-step
    fix this session: soft tool availability doesn't reliably get used)."""
    conn = connect()
    row = conn.execute(
        "SELECT title, description, content, n_cases_used, n_hits, n_misses FROM strategies WHERE fault_type = ?",
        (fault_type,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    title, description, content, n, hits, misses = row
    return {"title": title, "description": description, "content": content,
            "n_cases_used": n, "n_hits": hits, "n_misses": misses}


def distill_all_fault_types():
    conn = connect()
    fault_types = [r[0] for r in conn.execute("SELECT DISTINCT fault_type FROM cases").fetchall()]
    conn.close()
    results = {}
    for ft in fault_types:
        s = distill_strategy(ft)
        results[ft] = s
        print(f"{'OK' if s else 'SKIP (too few cases)'}: {ft}" + (f" -- {s['title']}" if s else ""), flush=True)
    return results


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "seed":
        n = seed_from_gold_cases()
        print(f"Seeded {n} new cases into agent memory.")
    elif len(sys.argv) > 1 and sys.argv[1] == "distill_all":
        distill_all_fault_types()
    elif len(sys.argv) > 1 and sys.argv[1] == "distill":
        print(json.dumps(distill_strategy(sys.argv[2]), indent=2))
    elif len(sys.argv) > 1:
        print(json.dumps(recall_similar_incidents(" ".join(sys.argv[1:])), indent=2))
    else:
        conn = connect()
        total = conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
        print(f"agent_memory.db: {total} cases stored.")
