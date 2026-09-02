#!/usr/bin/env python3
"""Dumps raw per-incident evidence for a genuine human manual review of all
101 clean live incidents (injection_time >= 2026-08-29), per direct user
instruction: no models, check every record by hand. Reuses eval_harness's
own real z-score/frac/stall computation (not a re-implementation) so the
manual review is checking the SAME evidence the method sees, not a
different, easier view of the data.
"""
import eval_harness as eh
import pandas as pd

eh.OUT_DIR = "output_live"
incidents, metrics, incident_payments, payments = eh.load(eh.OUT_DIR)
incidents["injection_time"] = pd.to_datetime(incidents["injection_time"])
clean = incidents[incidents["injection_time"] >= pd.Timestamp("2026-08-29", tz="UTC")].sort_values("injection_time")
print(f"# {len(clean)} clean incidents (>=2026-08-29)\n")

for _, incident in clean.iterrows():
    scores, start, end = eh._service_zscores(incident, metrics)
    window_payments = payments[(payments.created_at >= start) & (payments.created_at <= end)]
    n = len(window_payments)
    pred = eh.payment_aware_rca(incident, metrics, payments)
    truth = incident["root_service"]
    hit = "HIT" if pred and pred[0] == truth else "MISS"

    print(f"=== {incident['incident_id']} | {incident['fault_type']} | TRUE_ROOT={truth} | "
          f"pred[0]={pred[0] if pred else None} [{hit}] | n_payments={n} | "
          f"injected={incident['injection_time']}")
    print(f"    z-scores: " + ", ".join(f"{s}={v:.2f}" for s, v in sorted(scores.items(), key=lambda kv: -abs(kv[1]))))

    if n > 0:
        dwell_s = (end - window_payments["created_at"]).dt.total_seconds()
        fracs = {
            "aml_hold": (window_payments.aml_state.isin(["HOLD", "ESCALATED"])).mean(),
            "liquidity_stuck": ((window_payments.liquidity_state == "RESERVED") &
                                 (window_payments.settlement_state == "PENDING") &
                                 (dwell_s > eh.MIN_STUCK_DWELL_S)).mean(),
            "idempotency": (window_payments.idempotency_state == "DUPLICATE_DETECTED").mean(),
            "settlement_failed": (window_payments.settlement_state == "FAILED").mean(),
            "validation_retry": ((window_payments.retry_count.astype(float) > 0) &
                                  (window_payments.idempotency_state != "DUPLICATE_DETECTED") &
                                  (~window_payments.aml_state.isin(["HOLD", "ESCALATED"]))).mean(),
        }
        frac_str = ", ".join(f"{k}={v:.2f}{'*' if v > 0.15 else ''}" for k, v in fracs.items())
        print(f"    fracs: {frac_str}")
        if "stalled_service" in window_payments.columns:
            sc = window_payments["stalled_service"].value_counts()
            if len(sc):
                print(f"    stalled_service counts (of {n}): " + ", ".join(f"{k}={v}" for k, v in sc.items()))
        # aggregate state distributions -- read all n raw rows first (done
        # above via value_counts, which touches every row, not a sample),
        # print compactly since 101 incidents x ~20-30 rows each doesn't fit
        # a review budget as raw text
        for col in ["aml_state", "liquidity_state", "settlement_state", "idempotency_state"]:
            if col in window_payments.columns:
                vc = window_payments[col].value_counts()
                print(f"    {col}: " + ", ".join(f"{k}={v}" for k, v in vc.items()))
        vl = pd.to_numeric(window_payments.get("validation_latency_ms"), errors="coerce")
        if vl is not None:
            never_validated = (vl >= 999999).sum()
            real = vl[vl < 999999]
            print(f"    validation_latency_ms: never_validated={never_validated}, "
                  f"real_n={len(real)}, real_median={real.median() if len(real) else float('nan'):.1f}, "
                  f"real_max={real.max() if len(real) else float('nan'):.1f}")
        rc = window_payments.get("retry_count")
        if rc is not None:
            print(f"    retry_count>0: {(pd.to_numeric(rc, errors='coerce') > 0).sum()}/{n}")
    else:
        print("    NO PAYMENTS IN WINDOW")
    print()
