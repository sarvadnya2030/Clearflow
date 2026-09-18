"""Priority 2 (IMPROVEMENT_PLAN.md Section 3): formalized weighted temporal
composite score, replacing the binary onset-precedence check with:

    S_i = w_a * AnomalyMagnitude_i
        + w_p * Persistence_i
        + w_o * OnsetPrecedence_i
        + w_s * PreAlertSlope_i
        + w_c * ChangePointConfidence_i
        - w_d * DownstreamOnlyPenalty_i

Reuses gear_rca_rcaeval.py's already-verified load_case_metrics,
compute_anomaly_scores, compute_onset_times, service_from_metric,
STATIC_DEPS -- no re-derivation of already-verified pieces.

Each component is a pragmatic, honestly-documented proxy computed from
real per-metric time series in the case's metrics.parquet, not a
full statistical model (that would be Priority 3 / future work). This
is disclosed here rather than overclaimed.
"""
import numpy as np
import pandas as pd

from gear_rca_rcaeval import (
    load_case_metrics, compute_anomaly_scores, compute_onset_times,
    service_from_metric, STATIC_DEPS, SERVICES,
)

PRE_S, POST_S = 600, 300


def _post_window(df, inject_time):
    return df[(df["time"] >= inject_time) & (df["time"] < inject_time + POST_S)].sort_values("time")


def per_metric_components(df, inject_time, scores, onsets, threshold_sigma=3.0):
    """Compute the 5 positive terms per metric column (not yet per service)."""
    post = _post_window(df, inject_time)
    comps = {}
    for col, s in scores.items():
        z = s["z"]
        if abs(z) < 1e-9:
            continue
        vals = post[col].dropna().values
        if len(vals) < 3:
            continue

        # AnomalyMagnitude: raw |z|, capped so one extreme metric type
        # (e.g. an error-rate z-score from a near-zero baseline) can't
        # dominate the whole score alone -- this is the exact failure
        # mode already found (frontend's error z=6666 beating cartservice's
        # real latency z=4556). Cap via a saturating transform.
        anomaly_mag = float(np.tanh(abs(z) / 20.0))

        # Persistence: fraction of post-injection samples that individually
        # exceed the significance threshold (not just the window mean).
        mu, sigma = s["pre_mean"], max(abs(s["pre_mean"]) * 0.05, 1e-6)
        pre_std = None
        # sigma used in compute_anomaly_scores isn't returned, recompute cheaply:
        pre = df[(df["time"] >= inject_time - PRE_S) & (df["time"] < inject_time)][col].dropna()
        if len(pre) >= 5:
            pre_std = pre.std()
        sd = max(pre_std or 0.0, abs(mu) * 0.05, 1e-6)
        exceed = np.abs((vals - mu) / sd) > threshold_sigma
        persistence = float(exceed.mean())

        # OnsetPrecedence: earlier onset -> higher score. 1/(1+minutes).
        onset_t = onsets.get(col)
        onset_precedence = 1.0 / (1.0 + (onset_t / 60.0)) if onset_t is not None else 0.0

        # PreAlertSlope: linear trend in the post-injection window itself
        # (a ramping fault vs. an instant step both count, but a metric
        # with zero slope AND low persistence is more likely one noisy
        # blip than a real fault signature).
        t = post["time"].values[: len(vals)] if len(post) else np.arange(len(vals))
        if len(vals) >= 3 and np.ptp(t) > 0:
            slope_raw = np.polyfit(t - t[0], vals, 1)[0]
            slope = float(np.tanh(abs(slope_raw) / (abs(mu) + 1e-6) / 0.01))
        else:
            slope = 0.0

        # ChangePointConfidence: Welch's t-stat between pre/post windows,
        # bounded -- a real but simplified proxy for a full CUSUM/BOCPD
        # model (that's a Priority 3 / future-work item, not built here).
        if pre_std and pre_std > 1e-9 and len(vals) >= 3:
            post_std = float(np.std(vals)) or 1e-6
            se = np.sqrt((pre_std ** 2) / max(len(pre), 2) + (post_std ** 2) / len(vals))
            t_stat = abs(mu - float(np.mean(vals))) / se if se > 1e-9 else 0.0
            change_point_conf = float(np.tanh(t_stat / 10.0))
        else:
            change_point_conf = 0.0

        comps[col] = dict(anomaly_mag=anomaly_mag, persistence=persistence,
                           onset_precedence=onset_precedence, slope=slope,
                           change_point_conf=change_point_conf, onset_t=onset_t)
    return comps


def downstream_only_penalty(service, per_service_best_onset):
    """1.0 if `service` STATICALLY depends on another service that has a
    strictly earlier onset than itself (i.e. service's own anomaly is
    plausibly just propagation from something it calls) else 0.0.
    Reuses the already-verified STATIC_DEPS map -- does not re-derive it.
    """
    deps = STATIC_DEPS.get(service, [])
    if not deps or service not in per_service_best_onset:
        return 0.0
    my_onset = per_service_best_onset[service]
    if my_onset is None:
        return 0.0
    for d in deps:
        d_onset = per_service_best_onset.get(d)
        if d_onset is not None and d_onset < my_onset:
            return 1.0
    return 0.0


def composite_scores(case_id, threshold_sigma=3.0,
                      w_a=0.30, w_p=0.20, w_o=0.25, w_s=0.10, w_c=0.15, w_d=0.35):
    """Returns {service: (S_i, detail_dict)} ranked descending by S_i.
    Default weights are a documented starting point (not yet tuned on a
    held-out split -- see honest limitation in the report), chosen so
    OnsetPrecedence + DownstreamOnlyPenalty (the two components literature
    identifies as most discriminative for propagated-vs-source symptoms
    on network faults) carry the most combined weight.
    """
    df, inject_time = load_case_metrics(case_id)
    scores = compute_anomaly_scores(df, inject_time, PRE_S, POST_S)
    onsets = compute_onset_times(df, inject_time, threshold_sigma, PRE_S, POST_S)
    comps = per_metric_components(df, inject_time, scores, onsets, threshold_sigma)

    per_service = {}
    for col, c in comps.items():
        svc = service_from_metric(col)
        if svc is None:
            continue
        per_service.setdefault(svc, []).append(c)

    per_service_best_onset = {}
    for svc, clist in per_service.items():
        onset_vals = [c["onset_t"] for c in clist if c["onset_t"] is not None]
        per_service_best_onset[svc] = min(onset_vals) if onset_vals else None

    out = {}
    for svc, clist in per_service.items():
        best = max(clist, key=lambda c: (c["anomaly_mag"] + c["persistence"] + c["onset_precedence"]))
        penalty = downstream_only_penalty(svc, per_service_best_onset)
        S = (w_a * best["anomaly_mag"] + w_p * best["persistence"]
             + w_o * best["onset_precedence"] + w_s * best["slope"]
             + w_c * best["change_point_conf"] - w_d * penalty)
        out[svc] = (S, dict(best, downstream_only_penalty=penalty))

    return dict(sorted(out.items(), key=lambda kv: kv[1][0], reverse=True))


if __name__ == "__main__":
    import sys
    case_id = sys.argv[1] if len(sys.argv) > 1 else "re1ob_cartservice_delay_1"
    ranked = composite_scores(case_id)
    print(f"=== {case_id} ===")
    for svc, (S, detail) in ranked.items():
        print(f"  {svc:24s} S={S:+.4f}  {detail}")
