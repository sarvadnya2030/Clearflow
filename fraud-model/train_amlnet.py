#!/usr/bin/env python3
"""
Train the same 11-feature fraud model on AMLNet instead of PaySim, for a
fair, apples-to-apples comparison against the PaySim-trained baseline
(2026-08-30 retrain: Test ROC-AUC 0.6197, 186 fraud examples out of
400,000 training rows).

AMLNet has ~8.5x more positive examples (1,573 vs 186) and richer real
columns (category, real balance fields, real timestamps for velocity),
but is 100% Australia in this file -- country-risk/cross-border/currency
features will be degenerate here too, same known limitation as PaySim's
own zeroed crossBorder/velocity features. Kept in the same 11-feature
shape as FeatureEngineeringService.java on purpose, so this is a genuine
same-feature-space comparison, not a different, incomparable model.
"""
import re
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, classification_report

CSV_PATH = "/home/admin-/Downloads/AMLNet_August 2025.csv"
SAMPLE_SIZE = 1_090_000  # full file

TS_RE = re.compile(r"datetime\.datetime\((\d+), (\d+), (\d+), (\d+), (\d+), (\d+)")


def parse_timestamp(meta_str):
    m = TS_RE.search(meta_str)
    if not m:
        return pd.NaT
    y, mo, d, h, mi, s = (int(x) for x in m.groups())
    return pd.Timestamp(y, mo, d, h, mi, s)


def main():
    print(f"Loading AMLNet dataset ({SAMPLE_SIZE} rows)...")
    df = pd.read_csv(CSV_PATH, nrows=SAMPLE_SIZE)
    print(f"Loaded {len(df)} rows. Fraud rate: {df['isFraud'].mean()*100:.4f}%  (n={df['isFraud'].sum()})")

    print("Parsing real timestamps from metadata (for real velocity features)...")
    df["ts"] = df["metadata"].apply(parse_timestamp)
    df = df.sort_values("ts").reset_index(drop=True)

    # Real velocity: count of this debtor's (nameOrig) own prior transactions
    # in the last 1h/24h, computed from genuine chronological order -- same
    # spirit as VelocityCheckService.java, not a synthetic proxy.
    df["velocity_1h"] = 0
    df["velocity_24h"] = 0
    for name, grp in df.groupby("nameOrig", sort=False):
        idx = grp.index
        ts = grp["ts"].values
        v1h = np.zeros(len(ts), dtype=int)
        v24h = np.zeros(len(ts), dtype=int)
        for i in range(len(ts)):
            lo1 = np.searchsorted(ts, ts[i] - np.timedelta64(1, "h"))
            v1h[i] = i - lo1
            lo24 = np.searchsorted(ts, ts[i] - np.timedelta64(24, "h"))
            v24h[i] = i - lo24
        df.loc[idx, "velocity_1h"] = v1h
        df.loc[idx, "velocity_24h"] = v24h

    print("Computing isNewCreditorPair (first time this debtor->creditor pair appears)...")
    df["pair"] = df["nameOrig"] + "->" + df["nameDest"]
    df["is_new_pair"] = ~df.duplicated("pair", keep="first")

    print("Building feature matrix (same 11-feature shape as FeatureEngineeringService.java)...")
    amount_normalized = np.log10(df["amount"].astype(float) + 1.0) / 9.0
    hour_of_day = df["hour"].astype(float) / 23.0
    day_of_week = df["day_of_week"].astype(float) / 7.0
    is_weekend = (df["day_of_week"] >= 5).astype(float)  # AMLNet's day_of_week is 0-6
    # Degenerate on purpose -- this file is 100% Australia, same known
    # limitation as PaySim's own zeroed crossBorder/velocity features.
    debtor_country_risk = np.full(len(df), 0.1)
    creditor_country_risk = np.full(len(df), 0.1)
    cross_border = np.zeros(len(df))
    high_risk_currency = np.full(len(df), 0.2)  # AUD, low risk
    velocity_1h = np.minimum(100, df["velocity_1h"]) / 100.0
    velocity_24h = np.minimum(500, df["velocity_24h"]) / 500.0
    is_new_pair = df["is_new_pair"].astype(float)

    X = np.column_stack([
        amount_normalized, hour_of_day, day_of_week, is_weekend,
        debtor_country_risk, creditor_country_risk, cross_border,
        high_risk_currency, velocity_1h, velocity_24h, is_new_pair,
    ])
    y = df["isFraud"].values.astype(int)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    neg = (y_train == 0).sum()
    pos = (y_train == 1).sum()
    spw = neg / max(pos, 1)
    print(f"Train set: {len(y_train)} samples, pos={pos}, neg={neg}, scale_pos_weight={spw:.1f}")

    model = lgb.LGBMClassifier(
        n_estimators=300, learning_rate=0.05, max_depth=7, num_leaves=63,
        scale_pos_weight=spw, subsample=0.8, colsample_bytree=0.8,
        random_state=42, n_jobs=-1, verbose=-1,
    )
    model.fit(X_train, y_train)
    y_prob = model.predict_proba(X_test)[:, 1]
    auc = roc_auc_score(y_test, y_prob)
    print(f"\nTest ROC-AUC (AMLNet, same 11-feature space): {auc:.4f}")
    print(f"(comparison: PaySim baseline retrained tonight = 0.6197)")
    y_pred = (y_prob >= 0.5).astype(int)
    print(classification_report(y_test, y_pred, target_names=["Legit", "Fraud"], digits=3))

    imp = model.feature_importances_
    names = ["amountNormalized", "hourOfDay", "dayOfWeek", "isWeekend",
              "debtorCountryRisk", "creditorCountryRisk", "crossBorder",
              "highRiskCurrencyPair", "velocityLast1h", "velocityLast24h", "isNewCreditorPair"]
    print("\nFeature importances:")
    for n, i in sorted(zip(names, imp), key=lambda t: -t[1]):
        print(f"  {n:24s} {i}")


if __name__ == "__main__":
    main()
