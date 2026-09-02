#!/usr/bin/env python3
"""Loads the real ClearFlow-RCA benchmark data (incidents, evidence,
per-method predictions, known findings) into Neo4j as a queryable
knowledge graph -- "agent memory" for this project, since a lot of
interrelated data is being generated at once (101 incidents x 5+ methods
x per-case findings) and a flat CSV can't answer relationship questions
(e.g. "which incidents did every method miss on the same true root").

Idempotent: uses MERGE throughout, safe to re-run as more data lands in
model_comparison_results.csv.
"""
import pandas as pd
from neo4j import GraphDatabase

URI = "bolt://localhost:7687"
AUTH = ("neo4j", "clearflow-dev-graph")


def load_incidents(tx, incidents):
    for _, inc in incidents.iterrows():
        tx.run(
            """
            MERGE (i:Incident {id: $id})
            SET i.fault_type = $fault_type, i.fault_family = $fault_family,
                i.true_root = $true_root, i.injection_time = $injection_time,
                i.duration_seconds = $duration_seconds
            MERGE (s:Service {name: $true_root})
            MERGE (i)-[:TRUE_ROOT_CAUSE]->(s)
            """,
            id=inc["incident_id"], fault_type=inc["fault_type"],
            fault_family=inc["fault_family"], true_root=inc["root_service"],
            injection_time=str(inc["injection_time"]),
            duration_seconds=int(inc["duration_seconds"]),
        )


def load_predictions(tx, results):
    for _, row in results.iterrows():
        if not row["pred_rank1"] or pd.isna(row["pred_rank1"]):
            continue
        tx.run(
            """
            MATCH (i:Incident {id: $incident_id})
            MERGE (m:Method {name: $method})
            MERGE (s:Service {name: $pred})
            MERGE (i)-[p:PREDICTED_BY]->(m)
            SET p.pred_rank1 = $pred, p.hit = $hit, p.seconds = $seconds,
                p.timestamp = $timestamp
            MERGE (m)-[g:GUESSED]->(s)
            ON CREATE SET g.count = 1
            ON MATCH SET g.count = g.count + 1
            """,
            incident_id=row["incident_id"], method=row["method"],
            pred=row["pred_rank1"], hit=bool(row["hit"]),
            seconds=float(row["seconds"]), timestamp=str(row["timestamp"]),
        )


def load_findings(tx, findings):
    for f in findings:
        tx.run(
            """
            MERGE (f:Finding {id: $id})
            SET f.summary = $summary, f.date = $date, f.severity = $severity
            """,
            **f,
        )
        for inc_id in f.get("affected_incidents", []):
            tx.run(
                """
                MATCH (f:Finding {id: $fid}), (i:Incident {id: $iid})
                MERGE (f)-[:AFFECTS]->(i)
                """,
                fid=f["id"], iid=inc_id,
            )


# Real findings from this session's audit trail, worth being queryable
# alongside the incident/prediction graph rather than only living in
# markdown prose.
KNOWN_FINDINGS = [
    {"id": "jaeger-outage-2026-09-02", "date": "2026-09-02",
     "summary": "Jaeger down 13h, poisoned error_rate for all 8 services; fixed + hardened",
     "severity": "critical", "affected_incidents": []},
    {"id": "headline-number-unreproducible-2026-09-02", "date": "2026-09-02",
     "summary": "README's 0.406 payment_aware_rca headline was never reproducible; real number is 0.297",
     "severity": "critical", "affected_incidents": []},
    {"id": "settlement-cases-unsolvable", "date": "2026-09-01",
     "summary": "22/101 incidents (all settlement-root types) score 0% for every method: crash faults can't self-log",
     "severity": "structural", "affected_incidents": []},
    {"id": "topology-tie-margin-fixed-2026-09-02", "date": "2026-09-02",
     "summary": "TOPOLOGY_TIE_MARGIN 0.75->0.1: fixed graph_topology_baseline's 87% gateway-default bias; payment_aware_rca 0.297->0.416",
     "severity": "fixed", "affected_incidents": []},
]


def main():
    import eval_harness as eh
    eh.OUT_DIR = "output_live"
    incidents, metrics, incident_payments, payments = eh.load(eh.OUT_DIR)
    incidents["injection_time"] = pd.to_datetime(incidents["injection_time"])
    clean = incidents[incidents["injection_time"] >= pd.Timestamp("2026-08-29", tz="UTC")]

    try:
        results = pd.read_csv("model_comparison_results.csv")
    except FileNotFoundError:
        results = pd.DataFrame(columns=["incident_id", "method", "pred_rank1", "hit", "seconds", "timestamp"])

    # attach affected_incidents for the 22 known-unsolvable settlement cases
    unsolvable_ids = clean[clean.fault_type.isin(
        ["DB_TIMEOUT", "SETTLEMENT_DB_FAILURE_KAFKA_CONFOUND", "SETTLEMENT_DB_FAILURE_LIQUIDITY_CASCADE"]
    ) & (clean.root_service == "settlement")]["incident_id"].tolist()
    for f in KNOWN_FINDINGS:
        if f["id"] == "settlement-cases-unsolvable":
            f["affected_incidents"] = unsolvable_ids

    driver = GraphDatabase.driver(URI, auth=AUTH)
    with driver.session() as session:
        session.execute_write(load_incidents, clean)
        session.execute_write(load_predictions, results)
        session.execute_write(load_findings, KNOWN_FINDINGS)

        # sanity query -- confirm real graph structure, not just node dumps
        r = session.run(
            "MATCH (i:Incident)-[:TRUE_ROOT_CAUSE]->(s:Service) "
            "RETURN s.name AS root, count(i) AS n ORDER BY n DESC"
        )
        print("Incidents by true root service:")
        for row in r:
            print(f"  {row['root']}: {row['n']}")

        r = session.run(
            "MATCH (m:Method)-[p:PREDICTED_BY]-(i:Incident) "
            "RETURN m.name AS method, sum(CASE WHEN p.hit THEN 1 ELSE 0 END) AS hits, count(p) AS n "
            "ORDER BY n DESC"
        )
        print("\nMethod accuracy from graph (cross-check against CSV):")
        for row in r:
            print(f"  {row['method']}: {row['hits']}/{row['n']}")

    driver.close()
    print("\nLoaded into Neo4j. Browse at http://localhost:7474 (neo4j/clearflow-dev-graph)")


if __name__ == "__main__":
    main()
