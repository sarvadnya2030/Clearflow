#!/usr/bin/env python3
"""
ClearFlow Fraud Model — Training Script

Trains a real LightGBM binary classifier on synthetic payment data.
Feature space mirrors FeatureEngineeringService.java (11 features).

Features (in order, must match Java):
  0  amountNormalized      log10(amount+1) / 9
  1  hourOfDay             0-1 (UTC hour / 23)
  2  dayOfWeek             0-1 (ISO weekday / 7)
  3  isWeekend             0 or 1
  4  debtorCountryRisk     0-1 (country risk / 10)
  5  creditorCountryRisk   0-1
  6  crossBorder           0 or 1
  7  highRiskCurrencyPair  0-1 (currency risk / 10)
  8  velocityLast1h        0-1 (min(count,100)/100)
  9  velocityLast24h       0-1 (min(count,500)/500)
  10 isNewCreditorPair     0 or 1

Label: 1 = fraud, 0 = legitimate

Fraud rate target: ~8% (realistic for payment fraud)
"""

import os, json, math, random
import numpy as np
import lightgbm as lgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, classification_report, confusion_matrix

random.seed(42)
np.random.seed(42)

N_SAMPLES  = 200_000
FRAUD_RATE = 0.08

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(OUT_DIR, "fraud_model.lgb")
META_PATH  = os.path.join(OUT_DIR, "model_meta.json")

# ── Country risk mapping (mirrors CountryRiskMatrix.java) ─────────────────────
COUNTRY_RISK = {
    "DE": 1, "FR": 1, "NL": 1, "GB": 1, "SE": 1, "CH": 1, "AT": 1,
    "NO": 1, "DK": 1, "FI": 1, "BE": 1, "IT": 2, "ES": 2, "PT": 2,
    "PL": 2, "CZ": 2, "HU": 3, "RO": 3, "BG": 3, "HR": 3,
    "US": 2, "CA": 1, "AU": 1, "NZ": 1, "SG": 2, "JP": 2, "KR": 2,
    "HK": 3, "AE": 4, "SA": 4, "QA": 4, "BH": 4, "KW": 4,
    "IN": 4, "CN": 5, "BR": 5, "MX": 6, "ZA": 5, "TR": 6,
    "NG": 7, "EG": 6, "KE": 6, "GH": 5, "PK": 7, "BD": 6,
    "RU": 9, "BY": 8, "UA": 7, "KZ": 7, "AZ": 7,
    "IR": 10, "KP": 10, "SY": 10, "CU": 8, "SD": 9, "MM": 8,
    "VE": 8, "LY": 8, "IQ": 7, "YE": 8, "AF": 9, "ZW": 7,
    "LB": 7, "ML": 7, "SS": 8, "SO": 9, "CF": 8,
}

CURRENCY_RISK = {
    "EUR": 0.2, "GBP": 0.3, "CHF": 0.2, "USD": 0.3,
    "SEK": 0.2, "NOK": 0.2, "DKK": 0.2, "JPY": 0.2,
    "SGD": 0.2, "CAD": 0.2, "AUD": 0.2, "HKD": 0.3,
    "AED": 0.4, "SAR": 0.4, "TRY": 0.6, "BRL": 0.5,
    "MXN": 0.6, "ZAR": 0.5, "INR": 0.4, "CNY": 0.5,
    "RUB": 0.9, "IRR": 1.0, "KPW": 1.0,
}

HIGH_RISK_COUNTRIES  = {c for c, r in COUNTRY_RISK.items() if r >= 8}
MED_RISK_COUNTRIES   = {c for c, r in COUNTRY_RISK.items() if 5 <= r < 8}
LOW_RISK_COUNTRIES   = {c for c, r in COUNTRY_RISK.items() if r < 5}

ALL_COUNTRIES   = list(COUNTRY_RISK.keys())
ALL_CURRENCIES  = list(CURRENCY_RISK.keys())

def country_risk_norm(c):
    return COUNTRY_RISK.get(c, 5) / 10.0

def currency_risk_norm(c):
    return CURRENCY_RISK.get(c, 0.5)

def generate_sample(is_fraud):
    if is_fraud:
        # Fraud samples: combine multiple risk signals
        fraud_type = random.choices(
            ["high_country", "velocity", "large_amount", "new_pair_large", "off_hours", "mixed"],
            weights=[25, 20, 20, 15, 10, 10]
        )[0]

        if fraud_type == "high_country":
            debtor_country   = random.choice(list(LOW_RISK_COUNTRIES))
            creditor_country = random.choice(list(HIGH_RISK_COUNTRIES))
            amount = random.lognormvariate(11.0, 1.5)  # large amounts
            velocity_1h  = random.randint(0, 3) / 100.0
            velocity_24h = random.randint(0, 10) / 500.0
            new_pair = random.random() < 0.7

        elif fraud_type == "velocity":
            debtor_country   = random.choice(list(LOW_RISK_COUNTRIES))
            creditor_country = random.choice(list(LOW_RISK_COUNTRIES))
            amount = random.lognormvariate(9.0, 1.2)
            velocity_1h  = random.randint(30, 100) / 100.0   # high velocity
            velocity_24h = random.randint(100, 500) / 500.0
            new_pair = random.random() < 0.3

        elif fraud_type == "large_amount":
            debtor_country   = random.choice(list(LOW_RISK_COUNTRIES))
            creditor_country = random.choice(list(LOW_RISK_COUNTRIES | MED_RISK_COUNTRIES))
            amount = random.uniform(500_000, 5_000_000)       # very large
            velocity_1h  = random.randint(0, 5) / 100.0
            velocity_24h = random.randint(0, 20) / 500.0
            new_pair = random.random() < 0.85

        elif fraud_type == "new_pair_large":
            debtor_country   = random.choice(list(LOW_RISK_COUNTRIES))
            creditor_country = random.choice(list(MED_RISK_COUNTRIES | HIGH_RISK_COUNTRIES))
            amount = random.lognormvariate(10.5, 1.0)
            velocity_1h  = random.randint(0, 8) / 100.0
            velocity_24h = random.randint(0, 30) / 500.0
            new_pair = True

        elif fraud_type == "off_hours":
            debtor_country   = random.choice(list(LOW_RISK_COUNTRIES))
            creditor_country = random.choice(list(MED_RISK_COUNTRIES))
            amount = random.lognormvariate(9.5, 1.3)
            velocity_1h  = random.randint(5, 25) / 100.0
            velocity_24h = random.randint(20, 100) / 500.0
            new_pair = random.random() < 0.6
            # Force off-hours
            hour = random.choice([0, 1, 2, 3, 4, 22, 23])

        else:  # mixed — everything high
            debtor_country   = random.choice(list(MED_RISK_COUNTRIES))
            creditor_country = random.choice(list(HIGH_RISK_COUNTRIES))
            amount = random.lognormvariate(11.5, 1.0)
            velocity_1h  = random.randint(15, 60) / 100.0
            velocity_24h = random.randint(50, 200) / 500.0
            new_pair = True

        currency = random.choices(
            ALL_CURRENCIES,
            weights=[CURRENCY_RISK.get(c, 0.5) * 10 for c in ALL_CURRENCIES]
        )[0]
        if 'hour' not in dir():
            hour = random.randint(0, 23)
        cross_border = debtor_country != creditor_country

    else:
        # Legitimate samples: realistic business payment patterns
        debtor_country   = random.choices(
            ALL_COUNTRIES,
            weights=[max(0.1, 10 - COUNTRY_RISK.get(c, 5)) for c in ALL_COUNTRIES]
        )[0]
        creditor_country = random.choices(
            ALL_COUNTRIES,
            weights=[max(0.1, 10 - COUNTRY_RISK.get(c, 5)) for c in ALL_COUNTRIES]
        )[0]
        amount = random.lognormvariate(8.0, 1.4)  # typical retail/corporate
        amount = min(amount, 200_000)              # legit payments rarely exceed 200K
        currency = random.choices(
            ["EUR", "USD", "GBP", "CHF", "SEK", "JPY", "CAD", "SGD"],
            weights=[35, 30, 15, 8, 3, 3, 3, 3]
        )[0]
        # Business hours skewed
        hour = random.choices(
            range(24),
            weights=[1,1,1,1,1,2,4,8,10,10,10,9,8,9,10,10,9,8,6,5,4,3,2,1]
        )[0]
        velocity_1h  = random.choices(
            [i/100.0 for i in range(0, 20)],
            weights=[30,20,15,10,8,5,4,3,2,1,1,0.5,0.5,0.3,0.2,0.1,0.1,0.05,0.05,0.05]
        )[0]
        velocity_24h = random.uniform(0, 0.1)
        new_pair = random.random() < 0.2
        cross_border = random.random() < 0.35

    day = random.randint(1, 7)
    is_weekend = 1.0 if day >= 6 else 0.0

    features = [
        math.log10(max(amount, 1) + 1) / 9.0,
        hour / 23.0,
        day / 7.0,
        is_weekend,
        country_risk_norm(debtor_country),
        country_risk_norm(creditor_country),
        1.0 if cross_border else 0.0,
        currency_risk_norm(currency),
        velocity_1h,
        velocity_24h,
        1.0 if new_pair else 0.0,
    ]
    return features

print("=" * 60)
print("  ClearFlow Fraud Model — LightGBM Training")
print("=" * 60)
print(f"  Samples     : {N_SAMPLES:,}")
print(f"  Fraud rate  : {FRAUD_RATE*100:.0f}%")
print(f"  Features    : 11")

n_fraud = int(N_SAMPLES * FRAUD_RATE)
n_legit = N_SAMPLES - n_fraud

print(f"\n  Generating {n_legit:,} legitimate + {n_fraud:,} fraud samples...")

X_legit = [generate_sample(False) for _ in range(n_legit)]
X_fraud = [generate_sample(True)  for _ in range(n_fraud)]
X = np.array(X_legit + X_fraud, dtype=np.float32)
y = np.array([0] * n_legit + [1] * n_fraud, dtype=np.int32)

# Shuffle
idx = np.random.permutation(len(X))
X, y = X[idx], y[idx]

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

print(f"  Train: {len(X_train):,}  Test: {len(X_test):,}")
print("\n  Training LightGBM...")

train_data = lgb.Dataset(X_train, label=y_train)
val_data   = lgb.Dataset(X_test,  label=y_test, reference=train_data)

params = {
    "objective":        "binary",
    "metric":           "auc",
    "num_leaves":       63,
    "learning_rate":    0.05,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq":     5,
    "min_child_samples": 20,
    "lambda_l1":        0.1,
    "lambda_l2":        0.1,
    "verbose":          -1,
    "n_jobs":           -1,
    "scale_pos_weight": n_legit / n_fraud,  # handle class imbalance
}

model = lgb.train(
    params,
    train_data,
    num_boost_round=300,
    valid_sets=[val_data],
    callbacks=[lgb.early_stopping(30, verbose=False), lgb.log_evaluation(50)],
)

y_pred_proba = model.predict(X_test)
auc = roc_auc_score(y_test, y_pred_proba)
y_pred = (y_pred_proba >= 0.5).astype(int)

print(f"\n  AUC-ROC: {auc:.4f}")
print(f"\n  Classification report (threshold=0.5):")
print(classification_report(y_test, y_pred, target_names=["Legit", "Fraud"], digits=3))

feature_names = [
    "amountNormalized", "hourOfDay", "dayOfWeek", "isWeekend",
    "debtorCountryRisk", "creditorCountryRisk", "crossBorder",
    "highRiskCurrencyPair", "velocityLast1h", "velocityLast24h",
    "isNewCreditorPair",
]
importance = dict(zip(feature_names, model.feature_importance(importance_type="gain").tolist()))
importance_sorted = sorted(importance.items(), key=lambda x: -x[1])
print("  Feature importance (gain):")
for fname, imp in importance_sorted:
    bar = "█" * int(imp / max(v for _, v in importance_sorted) * 30)
    print(f"    {fname:<25} {bar}")

model.save_model(MODEL_PATH)
meta = {
    "model_version": "lgbm-v1",
    "auc": round(auc, 4),
    "n_estimators": model.num_trees(),
    "feature_names": feature_names,
    "fraud_rate_train": FRAUD_RATE,
    "threshold": 0.5,
}
with open(META_PATH, "w") as f:
    json.dump(meta, f, indent=2)

print(f"\n  Model saved → {MODEL_PATH}")
print(f"  Meta  saved → {META_PATH}")
print(f"  Trees: {model.num_trees()}  AUC: {auc:.4f}")
print("\n  Run fraud_model_server.py to serve on :8091")
