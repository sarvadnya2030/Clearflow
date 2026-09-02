"""
Empirical blast-radius model (2026-08-30).

Not a hand-assumed "downstream services get affected" graph -- that
assumption is exactly what graph_topology_baseline's confounder failures
(README v10-v11) showed is unreliable: a downstream slow call can spike an
UPSTREAM caller's own error rate via blocking/backpressure, so blast radius
isn't strictly pipeline-order.

Instead: for every real incident already collected (output_live/), measure
which OTHER services actually showed a real telemetry anomaly (z-score
spike) during that incident's own window, using the exact same
_service_zscores() function eval_harness.py's methods are scored with --
no separate, ad-hoc metric definition. Aggregate per root_service into an
empirical co-anomaly graph: P(service Y anomalous | service X is root).
This is real, data-derived, and falsifiable, not assumed.

Usage:
    python3 blast_radius.py                 # build + print the graph
    python3 blast_radius.py --validate       # leave-one-out sanity check
"""
import argparse
import sys
from collections import defaultdict

import pandas as pd

sys.path.insert(0, ".")
from eval_harness import load, _service_zscores, FULL_PIPELINE_ORDER

Z_THRESHOLD = 1.0  # "anomalous" cutoff -- same order of magnitude as
                    # payment_aware_rca's own TOPOLOGY_TIE_MARGIN=0.75,
                    # loose enough to catch real secondary spread, tight
                    # enough not to call background noise a co-failure.


def build_co_anomaly_graph(incidents, metrics, min_incidents_per_root=1):
    """Returns {root_service: {other_service: (count_affected, count_total)}}."""
    graph = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    per_root_incidents = defaultdict(int)

    for _, inc in incidents.iterrows():
        root = inc["root_service"]
        scores, _, _ = _service_zscores(inc, metrics)
        if not scores:
            continue  # no telemetry for this incident (e.g. pre-restart ES loss)
        per_root_incidents[root] += 1
        for svc in FULL_PIPELINE_ORDER:
            if svc == root:
                continue
            z = scores.get(svc, 0.0)
            graph[root][svc][1] += 1
            if abs(z) >= Z_THRESHOLD:
                graph[root][svc][0] += 1

    return graph, per_root_incidents


def print_graph(graph, per_root_incidents):
    print(f"{'='*70}\nEmpirical blast-radius graph (Z_THRESHOLD={Z_THRESHOLD})\n{'='*70}")
    for root in FULL_PIPELINE_ORDER:
        n = per_root_incidents.get(root, 0)
        if n < 1:
            print(f"\n{root}: no incidents rooted here yet")
            continue
        print(f"\n{root}  (n={n} real incidents)")
        edges = graph.get(root, {})
        ranked = sorted(edges.items(), key=lambda kv: kv[1][0] / kv[1][1] if kv[1][1] else 0, reverse=True)
        for svc, (affected, total) in ranked:
            p = affected / total if total else 0.0
            bar = "#" * int(p * 30)
            print(f"    -> {svc:24s} P(anomalous)={p:.2f} ({affected}/{total})  {bar}")


def validate_leave_one_out(incidents, metrics):
    """For each incident, predict its blast radius from the OTHER incidents'
    empirical graph (leave-this-one-out), then check whether the actual
    n_affected_payments/propagation_depth for THIS incident is consistent
    with what the model predicted for its root_service. Honest check: this
    is a model built from small n (often 1-9 incidents per root), so treat
    results as directional, not a strong claim -- reported with n visible.
    """
    print(f"\n{'='*70}\nLeave-one-out validation\n{'='*70}")
    rows = []
    for i, (_, inc) in enumerate(incidents.iterrows()):
        others = incidents.drop(incidents.index[i])
        graph, counts = build_co_anomaly_graph(others, metrics)
        root = inc["root_service"]
        edges = graph.get(root, {})
        predicted_spread = sum(1 for svc, (a, t) in edges.items() if t > 0 and a / t >= 0.5)
        scores, _, _ = _service_zscores(inc, metrics)
        actual_spread = sum(1 for svc, z in scores.items() if svc != root and abs(z) >= Z_THRESHOLD)
        rows.append({
            "incident_id": inc.get("incident_id", i),
            "root": root,
            "predicted_spread": predicted_spread,
            "actual_spread": actual_spread,
            "n_affected_payments": inc.get("n_affected_payments"),
        })
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))
    match = (df["predicted_spread"] == df["actual_spread"]).mean()
    print(f"\nExact predicted==actual spread-count match: {match:.2f} (n={len(df)})")
    corr = df["predicted_spread"].corr(df["actual_spread"])
    print(f"Correlation(predicted_spread, actual_spread): {corr:.2f}" if pd.notna(corr) else "Correlation: undefined (no variance)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="output_live")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--lookback-hours", type=float, default=0.05,
                     help="Pre-incident baseline window -- default matches live_evidence.py's "
                          "own default (3min), safe for incidents packed minutes apart. Use 2 "
                          "for the synthetic dataset's spread-over-30-days incidents instead.")
    args = ap.parse_args()

    import eval_harness as eh
    eh.LOOKBACK_HOURS = args.lookback_hours

    incidents, metrics, incident_payments, payments = load(args.out_dir)
    sorted_inc = incidents.sort_values("injection_time").reset_index(drop=True)
    today = sorted_inc[sorted_inc["injection_time"] >= "2026-08-29"]

    graph, counts = build_co_anomaly_graph(today, metrics)
    print_graph(graph, counts)

    if args.validate:
        validate_leave_one_out(today, metrics)


if __name__ == "__main__":
    main()
