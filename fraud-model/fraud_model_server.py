#!/usr/bin/env python3
"""
ClearFlow Fraud Model Server — port 8091

REST endpoint consumed by LightGBMStubClient.java:
  POST /predict
    body: { "features": [f0..f10], "metadata": { "paymentId": "..", "currency": ".." } }
    resp: { "score": 0.23, "featureImportance": {...}, "modelVersion": "lgbm-v1" }

  GET /health   → { "status": "UP", "model": "lgbm-v1", "auc": 0.9842 }
  GET /metrics  → { "total_predictions": N, "fraud_rate_live": X, "avg_score": Y }
"""

import os, json, time, threading
from collections import deque

import numpy as np
import lightgbm as lgb
from flask import Flask, request, jsonify

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "fraud_model.lgb")
META_PATH  = os.path.join(BASE_DIR, "model_meta.json")

app = Flask(__name__)

# ── Load model ────────────────────────────────────────────────────────────────
print(f"Loading model from {MODEL_PATH}...")
if not os.path.exists(MODEL_PATH):
    print("ERROR: model not found. Run train.py first.")
    exit(1)

model = lgb.Booster(model_file=MODEL_PATH)
with open(META_PATH) as f:
    meta = json.load(f)

FEATURE_NAMES = meta["feature_names"]
MODEL_VERSION = meta["model_version"]
AUC           = meta["auc"]
print(f"Model loaded: {MODEL_VERSION}  AUC={AUC}  Trees={model.num_trees()}")

# ── Live metrics ──────────────────────────────────────────────────────────────
lock             = threading.Lock()
total_preds      = 0
fraud_count      = 0
recent_scores    = deque(maxlen=1000)
pred_times_ms    = deque(maxlen=1000)

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "UP", "model": MODEL_VERSION, "auc": AUC})

@app.route("/metrics", methods=["GET"])
def metrics():
    with lock:
        n     = total_preds
        fr    = fraud_count / n if n > 0 else 0.0
        avg   = float(np.mean(recent_scores)) if recent_scores else 0.0
        p99ms = float(np.percentile(list(pred_times_ms), 99)) if pred_times_ms else 0.0
    return jsonify({
        "total_predictions": n,
        "fraud_rate_live":   round(fr, 4),
        "avg_score":         round(avg, 4),
        "p99_latency_ms":    round(p99ms, 2),
        "model_version":     MODEL_VERSION,
    })

@app.route("/predict", methods=["POST"])
def predict():
    t0 = time.monotonic()
    body = request.get_json(force=True)

    features  = body.get("features", [])
    metadata  = body.get("metadata", {})

    if len(features) != len(FEATURE_NAMES):
        return jsonify({"error": f"Expected {len(FEATURE_NAMES)} features, got {len(features)}"}), 400

    X = np.array([features], dtype=np.float32)
    score = float(model.predict(X)[0])

    # Per-feature SHAP-style contribution (fast approximation using feature importance × feature value)
    importances = model.feature_importance(importance_type="gain")
    total_imp   = importances.sum() or 1.0
    feature_importance = {
        name: round(float(imp / total_imp) * score * feat, 4)
        for name, imp, feat in zip(FEATURE_NAMES, importances, features)
    }

    elapsed_ms = (time.monotonic() - t0) * 1000
    with lock:
        global total_preds, fraud_count
        total_preds   += 1
        if score >= 0.5:
            fraud_count += 1
        recent_scores.append(score)
        pred_times_ms.append(elapsed_ms)

    return jsonify({
        "score":             round(score, 4),
        "featureImportance": feature_importance,
        "modelVersion":      MODEL_VERSION,
        "latencyMs":         round(elapsed_ms, 2),
    })

if __name__ == "__main__":
    print(f"Starting fraud model server on :8091")
    app.run(host="0.0.0.0", port=8091, threaded=True)
