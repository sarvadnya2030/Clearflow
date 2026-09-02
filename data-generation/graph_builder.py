#!/usr/bin/env python3
"""
ClearFlow-RCA graph builder (Module 6).

Builds the causal knowledge graph per data-generation/graph_schema.md
(Module 3) from the existing dataset files, and provides tiered evidence
views (G0-G4) so a method under evaluation only ever receives the subgraph
it's supposed to see -- enforcing the ground-truth leak fix from Module 3 in
code, not just in documentation.

This module builds the GRAPH. It does not implement any RCA method -- that's
Module 8/9 (baseline / payment-aware RCA), which consume the tiers this
module produces.

Node types: Service, PaymentEvent, Payment, Account, MetricWindow, Incident
Edge kinds: structural, temporal, causal_within, causal_cross (leak, held out)

Usage:
    python3 graph_builder.py            # build, extract tiers, verify, report
"""

import csv
from collections import defaultdict
from datetime import datetime

import networkx as nx

OUT_DIR = "data-generation/output"
METRIC_WINDOW_MIN = 30  # aggregate 5-min metric samples into 30-min windows

PROPAGATION_CHAINS = {
    "gateway": ["gateway"],
    "validation-enrichment": ["validation-enrichment", "aml-compliance", "routing-execution", "settlement"],
    "aml-compliance": ["aml-compliance", "routing-execution", "settlement"],
    "routing-execution": ["routing-execution", "settlement"],
    "settlement": ["settlement"],
}
SERVICES = ["gateway", "validation-enrichment", "aml-compliance", "routing-execution", "settlement"]

# tier -> which edge kinds are included, cumulative
TIER_EDGE_KINDS = {
    "G0": {"structural_topology"},
    "G1": {"structural_topology", "structural_membership", "temporal"},
    "G2": {"structural_topology", "structural_membership", "temporal", "structural_metric"},
    "G3": {"structural_topology", "structural_membership", "temporal", "structural_metric", "payment_state"},
    "G4": {"structural_topology", "structural_membership", "temporal", "structural_metric", "payment_state", "causal_within"},
}
# ground-truth-only edge/node kinds, NEVER included in any G-tier
GROUND_TRUTH_KINDS = {"causal_cross", "incident_root", "incident_affects"}


def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def parse_dt(s):
    return datetime.fromisoformat(s)


def build_full_graph():
    payments = read_csv(f"{OUT_DIR}/clearflow_rca_dataset.csv")
    events = read_csv(f"{OUT_DIR}/payment_events.csv")
    accounts = read_csv(f"{OUT_DIR}/accounts.csv")
    metrics = read_csv(f"{OUT_DIR}/metrics.csv")
    incidents = read_csv(f"{OUT_DIR}/incidents.csv")
    incident_payments = read_csv(f"{OUT_DIR}/incident_payments.csv")

    G = nx.MultiDiGraph()

    # --- Service nodes + STRUCTURAL topology edges (the real, full pipeline
    #     order -- NOT the incident PROPAGATION_CHAINS below, which model
    #     fault blast-radius from a given root service and deliberately omit
    #     gateway as a root; using them here would silently drop gateway
    #     from the topology view entirely) ---
    FULL_PIPELINE_ORDER = ["gateway", "validation-enrichment", "aml-compliance", "routing-execution", "settlement"]
    for svc in SERVICES:
        G.add_node(f"svc::{svc}", node_type="Service", name=svc)
    for a, b in zip(FULL_PIPELINE_ORDER, FULL_PIPELINE_ORDER[1:]):
        G.add_edge(f"svc::{a}", f"svc::{b}", kind="structural_topology", relation="CALLS")

    # --- Account nodes ---
    for acc in accounts:
        G.add_node(f"acct::{acc['account_id']}", node_type="Account", **acc)

    # --- MetricWindow nodes: aggregate metrics.csv into 30-min buckets/service,
    #     with a z-score anomaly relative to that service's own global baseline ---
    baseline = defaultdict(lambda: {"error_rate": [], "p99_latency_ms": [], "kafka_lag": [], "cpu_pct": []})
    for m in metrics:
        for f in ("error_rate", "p99_latency_ms", "kafka_lag", "cpu_pct"):
            baseline[m["service"]][f].append(float(m[f]))
    base_stats = {}
    for svc, vals in baseline.items():
        base_stats[svc] = {f: (sum(v) / len(v), (sum((x - sum(v) / len(v)) ** 2 for x in v) / len(v)) ** 0.5 or 1e-6)
                            for f, v in vals.items()}

    window_bucket = defaultdict(list)
    for m in metrics:
        ts = parse_dt(m["timestamp"])
        bucket = ts.replace(minute=(ts.minute // METRIC_WINDOW_MIN) * METRIC_WINDOW_MIN, second=0, microsecond=0)
        window_bucket[(m["service"], bucket)].append(m)

    for (svc, bucket), rows in window_bucket.items():
        wid = f"mw::{svc}::{bucket.isoformat()}"
        avg = {f: sum(float(r[f]) for r in rows) / len(rows) for f in ("error_rate", "p99_latency_ms", "kafka_lag", "cpu_pct")}
        mu, sigma = base_stats[svc]["error_rate"]
        anomaly_score = (avg["error_rate"] - mu) / sigma
        G.add_node(wid, node_type="MetricWindow", service=svc, window_start=bucket.isoformat(),
                    anomaly_score=round(anomaly_score, 3), **{f"avg_{k}": round(v, 4) for k, v in avg.items()})
        G.add_edge(f"svc::{svc}", wid, kind="structural_metric", relation="EMITS")

    # --- Payment + PaymentEvent nodes ---
    for p in payments:
        pid = f"pay::{p['payment_id']}"
        G.add_node(pid, node_type="Payment", **p)
        G.add_edge(pid, f"acct::{p['debtor_id']}", kind="structural_membership", relation="INVOLVES", role="debtor")
        G.add_edge(pid, f"acct::{p['creditor_id']}", kind="structural_membership", relation="INVOLVES", role="creditor")

    event_payment_of = {e["event_id"]: e["payment_id"] for e in events}

    for e in events:
        eid = f"ev::{e['event_id']}"
        G.add_node(eid, node_type="PaymentEvent", **e)
        pid = f"pay::{e['payment_id']}"
        G.add_edge(eid, pid, kind="structural_membership", relation="BELONGS_TO")
        if e["service"] in SERVICES:
            G.add_edge(eid, f"svc::{e['service']}", kind="structural_membership", relation="OCCURS_AT")
        if e["parent_event_id"]:
            G.add_edge(f"ev::{e['parent_event_id']}", eid, kind="temporal", relation="NEXT")
        if e["caused_by"]:
            cause_payment = event_payment_of.get(e["caused_by"])
            edge_kind = "causal_within" if cause_payment == e["payment_id"] else "causal_cross"
            G.add_edge(f"ev::{e['caused_by']}", eid, kind=edge_kind, relation="CAUSED")

    # payment-state edges (Payment node's own state fields are already node
    # attributes, added above -- G3 access is "attributes visible", not extra
    # edges; this keeps the schema simple and matches Module 3's doc)

    # --- Incident (ground truth) nodes + edges -- NEVER included in G0-G4 ---
    for inc in incidents:
        iid = f"inc::{inc['incident_id']}"
        G.add_node(iid, node_type="Incident", **inc)
        if inc["root_event_id"]:
            G.add_edge(iid, f"ev::{inc['root_event_id']}", kind="incident_root", relation="ROOT_CAUSE_OF")
    for row in incident_payments:
        G.add_edge(f"inc::{row['incident_id']}", f"pay::{row['payment_id']}", kind="incident_affects", relation="AFFECTS")

    return G


def extract_tier(G, tier):
    """Returns the subgraph a method at evidence tier `tier` is allowed to
    see: only nodes/edges of the cumulative kinds for that tier, and NEVER
    any Incident node or ground-truth-only edge kind, regardless of tier.
    """
    allowed_kinds = TIER_EDGE_KINDS[tier]
    edges = [(u, v, k) for u, v, k, d in G.edges(keys=True, data=True) if d["kind"] in allowed_kinds]
    sub = G.edge_subgraph([(u, v, k) for u, v, k in edges]).copy()
    # G3+ also needs Payment node attributes (state fields) visible even for
    # payments with no qualifying edges in-view; G0-G2 should NOT have those
    # attributes readable, so strip them for lower tiers.
    if tier in ("G0", "G1", "G2"):
        for n, d in sub.nodes(data=True):
            if d.get("node_type") == "Payment":
                for f in ("aml_state", "liquidity_state", "idempotency_state", "settlement_state",
                           "finalized", "laundering_typology", "aml_risk_score"):
                    d.pop(f, None)
    return sub


def verify_no_leak(G):
    """Hard assertions: no G-tier may ever contain an Incident node or a
    ground-truth-only edge kind. This is the Module 3 leak fix enforced in
    code, not just documented.
    """
    for tier in TIER_EDGE_KINDS:
        sub = extract_tier(G, tier)
        incident_nodes = [n for n, d in sub.nodes(data=True) if d.get("node_type") == "Incident"]
        gt_edges = [1 for _, _, d in sub.edges(data=True) if d["kind"] in GROUND_TRUTH_KINDS]
        assert not incident_nodes, f"LEAK: {tier} contains {len(incident_nodes)} Incident nodes"
        assert not gt_edges, f"LEAK: {tier} contains {len(gt_edges)} ground-truth edges"
    print("Leak verification passed: no tier (G0-G4) exposes Incident nodes or ground-truth edge kinds.")


def main():
    print("Building full graph (all node/edge types, including ground truth)...")
    G = build_full_graph()
    print(f"Full graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    by_type = defaultdict(int)
    for _, d in G.nodes(data=True):
        by_type[d["node_type"]] += 1
    print("Nodes by type:", dict(by_type))

    by_kind = defaultdict(int)
    for _, _, d in G.edges(data=True):
        by_kind[d["kind"]] += 1
    print("Edges by kind:", dict(by_kind))

    print("\nExtracting evidence tiers G0-G4...")
    for tier in TIER_EDGE_KINDS:
        sub = extract_tier(G, tier)
        print(f"  {tier}: {sub.number_of_nodes()} nodes, {sub.number_of_edges()} edges")

    print()
    verify_no_leak(G)

    causal_cross = sum(1 for _, _, d in G.edges(data=True) if d["kind"] == "causal_cross")
    causal_within = sum(1 for _, _, d in G.edges(data=True) if d["kind"] == "causal_within")
    print(f"\ncausal_within edges (legitimate, in G4): {causal_within}")
    print(f"causal_cross edges (the leak, held out of every tier): {causal_cross}")


if __name__ == "__main__":
    main()
