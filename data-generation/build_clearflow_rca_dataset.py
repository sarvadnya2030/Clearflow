#!/usr/bin/env python3
"""
ClearFlow-RCA synthetic dataset generator (v2).

Produces three related artifacts instead of one flat CSV, per the
architectural review in data-generation/README.md:

  output/accounts.csv        -- persistent debtor/creditor profiles
  output/clearflow_rca_dataset.csv  -- payments (v2 schema)
  output/payment_events.csv  -- causal state-transition timeline per payment
                                 (Module 5A: this is what lets a graph builder
                                 reconstruct causal propagation, not just a
                                 final-state snapshot)

Design principles carried over from the review:
  - Rail selection is conditioned on currency and amount (SEPA_INSTANT/GBP
    rails/USD rails are not currency-agnostic in reality; each rail has a
    real value ceiling).
  - Accounts are persistent entities with a home country/currency/risk tier,
    not redrawn per row -- this is what makes cross-border/embargo/velocity
    signals meaningful.
  - AML/fraud fields exist ONLY to produce realistic fault preconditions
    (AML_state feeding the fault taxonomy) -- fraud detection itself is
    explicitly NOT a research contribution of this project.
  - The base corpus is deliberately fault-free at the SYSTEM level: a ~2%
    ordinary settlement failure rate exists (real payment systems have
    routine failures), but no systemic incident is baked in here. Module 7's
    fault injector owns all incident semantics; this generator must not
    pre-empt it.
  - Kept deliberately un-fancy: fee ratios and timestamp-of-day distribution
    are left as simple constants, per the rule "don't polish fields that
    don't feed a service decision, state transition, or fault precondition."
"""

import csv
import hashlib
import math
import os
import random
import uuid
from datetime import datetime, timedelta

random.seed(42)

N_PAYMENTS = 50_000
SIM_DAYS = 30
START = datetime(2026, 7, 1)
OUT_DIR = "data-generation/output"

# ---------------------------------------------------------------------------
# Currency / rail / country model
# ---------------------------------------------------------------------------

# PaymentRail enum, ported verbatim from
# routing-execution/src/main/java/com/clearflow/routing/domain/PaymentRail.java
# limit_amount = None means "no realistic ceiling for this rail" (CHAPS/FEDWIRE/
# TARGET2/CHIPS/SWIFT are high-value / unlimited by design).
RAIL_INFO = {
    "INTERNAL":              {"priority": 0,  "expected_s": 0,      "limit": None},
    "SEPA_INSTANT":          {"priority": 1,  "expected_s": 10,     "limit": 100_000},
    "SEPA_CREDIT_TRANSFER":  {"priority": 2,  "expected_s": 86_400, "limit": None},
    "FASTER_PAYMENTS":       {"priority": 3,  "expected_s": 7_200,  "limit": 1_000_000},
    "CHAPS":                 {"priority": 4,  "expected_s": 14_400, "limit": None},
    "FEDWIRE":               {"priority": 5,  "expected_s": 14_400, "limit": None},
    "FEDACH":                {"priority": 6,  "expected_s": 86_400, "limit": 100_000},
    "CHIPS":                 {"priority": 7,  "expected_s": 86_400, "limit": None},
    "SWIFT_GPI":              {"priority": 8,  "expected_s": 172_800, "limit": None},
    "SWIFT_MT103":            {"priority": 9,  "expected_s": 259_200, "limit": None},
    "TARGET2":                {"priority": 10, "expected_s": 86_400,  "limit": None},
    "BACS":                   {"priority": 11, "expected_s": 259_200, "limit": 20_000_000},
}

# Real currency-zone rail eligibility -- a payment can only travel domestic
# rails that actually clear its currency.
CURRENCY_DOMESTIC_RAILS = {
    "EUR": ["SEPA_INSTANT", "SEPA_CREDIT_TRANSFER", "TARGET2", "INTERNAL"],
    "GBP": ["FASTER_PAYMENTS", "CHAPS", "BACS", "INTERNAL"],
    "USD": ["FEDWIRE", "FEDACH", "CHIPS", "INTERNAL"],
}
CROSS_BORDER_RAILS = ["SWIFT_GPI", "SWIFT_MT103"]

CURRENCY_COUNTRIES = {
    "EUR": ["DE", "FR", "NL", "IT", "ES", "IE", "BE", "AT"],
    "GBP": ["GB"],
    "USD": ["US"],
    "AUD": ["AU"],
    "SGD": ["SG"],
}
CURRENCY_WEIGHTS = {"EUR": 0.35, "USD": 0.30, "GBP": 0.15, "AUD": 0.10, "SGD": 0.10}
EMBARGO_COUNTRIES = ["IR", "KP", "SY", "CU", "SD", "RU"]  # matches
# validation/application-dev.yml clearflow.embargo.countries

CROSS_BORDER_PROB = 0.16
EMBARGO_CORRIDOR_RATE = 0.01  # rare, deliberately: exercises EmbargoPreCheckProcessor

# ---------------------------------------------------------------------------
# Payment-type / amount model (PaySim-informed medians, now capped so a
# rail's real ceiling and a sane retail/corporate tail are both respected)
# ---------------------------------------------------------------------------
PAYMENT_TYPES = ["PAYMENT", "TRANSFER", "CASH_IN", "CASH_OUT", "DEBIT"]
PAYMENT_TYPE_WEIGHTS = [0.34, 0.17, 0.22, 0.20, 0.07]
AMOUNT_MEDIAN_BY_TYPE = {
    "PAYMENT": 9_362.82, "TRANSFER": 581_073.79,
    "CASH_IN": 151_993.67, "CASH_OUT": 168_271.66, "DEBIT": 3_601.51,
}
AMOUNT_SIGMA = 0.6
AMOUNT_CAP_MULTIPLIER = 6  # hard cap at 6x the type's median -- kills the
                            # unrealistic long tail (was hitting EUR 19M before)

CHANNELS = ["MOBILE", "WEB", "ATM", "API"]
CHANNEL_WEIGHTS = [0.55, 0.28, 0.09, 0.08]
PAYMENT_METHODS = ["ACCOUNT_NUMBER", "CARD", "PAY_ID"]
PAYMENT_METHOD_WEIGHTS = [0.40, 0.30, 0.30]

# fee ratios -- left as flat constants deliberately (see module docstring)
FEE_INTERNAL_RATIO = 0.0033
FEE_EXTERNAL_RATIO = 0.0267

# ---------------------------------------------------------------------------
# Account model (persistent -- this is what makes corridor/velocity/risk
# signals mean something instead of being independent per-row noise)
# ---------------------------------------------------------------------------
N_DEBTORS = 8_000
N_CREDITORS = 3_000
HIGH_RISK_ACCOUNT_RATE = 0.02   # small pool of recidivist high-risk accounts
PEP_RATE = 0.001


def weighted_choice(options, weights):
    return random.choices(options, weights=weights, k=1)[0]


def make_accounts(n, prefix):
    accounts = []
    for i in range(n):
        currency = weighted_choice(list(CURRENCY_WEIGHTS), list(CURRENCY_WEIGHTS.values()))
        country = random.choice(CURRENCY_COUNTRIES[currency])
        risk_tier = "high" if random.random() < HIGH_RISK_ACCOUNT_RATE else \
                    ("medium" if random.random() < 0.08 else "low")
        is_pep = random.random() < PEP_RATE
        avg_amount = round(random.lognormvariate(math.log(8_000), 0.8), 2)
        accounts.append({
            "account_id": f"{prefix}-{i:07d}",
            "account_type": "customer" if prefix == "CUST" else "merchant",
            "home_country": country,
            "home_currency": currency,
            "risk_tier": risk_tier,
            "is_pep": is_pep,
            "avg_amount": avg_amount,
        })
    return accounts


def synth_amount(payment_type):
    median = AMOUNT_MEDIAN_BY_TYPE[payment_type]
    val = random.lognormvariate(math.log(median), AMOUNT_SIGMA)
    return round(min(val, median * AMOUNT_CAP_MULTIPLIER), 2)


def pick_creditor(debtor, creditors_by_currency, is_cross_border_intent):
    currency = debtor["home_currency"]
    if is_cross_border_intent:
        other_currencies = [c for c in creditors_by_currency if c != currency]
        pool_currency = random.choice(other_currencies)
    else:
        pool_currency = currency
    return random.choice(creditors_by_currency[pool_currency])


def pick_rail_and_currency(debtor, creditor, amount):
    currency = debtor["home_currency"]
    has_domestic_rail = currency in CURRENCY_DOMESTIC_RAILS
    different_zone = debtor["home_currency"] != creditor["home_currency"]

    # AUD/SGD have no domestic rail modeled in this system (matches the real
    # PaymentRail enum, which only has EUR/GBP/USD domestic rails) -- those
    # always clear cross-border via SWIFT, which is realistic.
    is_cross_border = (not has_domestic_rail) or different_zone

    if is_cross_border:
        eligible = list(CROSS_BORDER_RAILS)
    else:
        domestic = CURRENCY_DOMESTIC_RAILS[currency]
        eligible = [r for r in domestic if RAIL_INFO[r]["limit"] is None or amount <= RAIL_INFO[r]["limit"]]
        if not eligible:
            eligible = [r for r in domestic if RAIL_INFO[r]["limit"] is None]

    rail = random.choice(eligible)
    return rail, currency, is_cross_border


def derive_aml_state(typology, category_risk, risk_score, is_pep, embargo_hit):
    if embargo_hit:
        return "REJECTED"
    if typology in ("layering", "integration"):
        return "ESCALATED"
    if typology == "structuring" or category_risk == "high" or is_pep:
        return "HOLD"
    if category_risk == "medium" and risk_score > 70:
        return "HOLD"
    return "CLEAR"


def derive_payment_state(aml_state, settlement_state):
    if aml_state in ("HOLD", "ESCALATED", "REJECTED"):
        return "BLOCKED" if aml_state != "REJECTED" else "REJECTED"
    if settlement_state == "FAILED":
        return "FAILED"
    if settlement_state == "SETTLED":
        return "SETTLED"
    return "LIQUIDITY_RESERVED"


TYPOLOGIES = ["normal", "structuring", "layering", "integration"]
TYPOLOGY_WEIGHTS = [0.9980, 0.00033, 0.00162, 0.00005]
CATEGORY_RISK = ["low", "medium", "high"]
CATEGORY_RISK_WEIGHTS = [0.65, 0.348, 0.002]
SETTLEMENT_WEIGHTS = {"SETTLED": 0.94, "PENDING": 0.04, "FAILED": 0.02}


def build_payment(i, debtors, creditors_by_currency, event_id_counter):
    payment_id = f"PAY-{i:08d}"
    uetr = str(uuid.uuid4())
    created_at = START + timedelta(seconds=random.randint(0, SIM_DAYS * 86400))

    debtor = random.choice(debtors)
    has_domestic_rail = debtor["home_currency"] in CURRENCY_DOMESTIC_RAILS
    cross_border_intent = (not has_domestic_rail) or random.random() < CROSS_BORDER_PROB
    creditor = pick_creditor(debtor, creditors_by_currency, cross_border_intent)

    payment_type = weighted_choice(PAYMENT_TYPES, PAYMENT_TYPE_WEIGHTS)
    amount = synth_amount(payment_type)
    rail, currency, is_cross_border = pick_rail_and_currency(debtor, creditor, amount)

    embargo_hit = random.random() < EMBARGO_CORRIDOR_RATE
    creditor_country = random.choice(EMBARGO_COUNTRIES) if embargo_hit else creditor["home_country"]

    channel = weighted_choice(CHANNELS, CHANNEL_WEIGHTS)
    payment_method = weighted_choice(PAYMENT_METHODS, PAYMENT_METHOD_WEIGHTS)

    category_risk = weighted_choice(CATEGORY_RISK, CATEGORY_RISK_WEIGHTS)
    if embargo_hit:
        category_risk = "high"
    risk_score = min(max(round(random.gauss(55.6, 9.27), 2), 0), 100)
    if debtor["risk_tier"] == "high":
        risk_score = min(risk_score + 20, 100)
    typology = "normal" if embargo_hit else weighted_choice(TYPOLOGIES, TYPOLOGY_WEIGHTS)
    if debtor["risk_tier"] == "high" and typology == "normal" and random.random() < 0.05:
        typology = weighted_choice(["structuring", "layering"], [0.7, 0.3])

    aml_state = derive_aml_state(typology, category_risk, risk_score, debtor["is_pep"], embargo_hit)
    is_fraud = 1 if (typology != "normal" or embargo_hit) else 0
    amount_vs_account_avg = round(amount / max(debtor["avg_amount"], 1.0), 3)

    fee_internal = round(amount * FEE_INTERNAL_RATIO, 2)
    fee_external = round(amount * FEE_EXTERNAL_RATIO, 2)

    idempotency_key = hashlib.sha256(
        f"{debtor['account_id']}|{amount}|{creditor['account_id']}".encode()
    ).hexdigest()[:16]

    settlement_state = weighted_choice(list(SETTLEMENT_WEIGHTS), list(SETTLEMENT_WEIGHTS.values()))
    if aml_state in ("HOLD", "ESCALATED", "REJECTED"):
        settlement_state = "PENDING" if aml_state != "REJECTED" else "FAILED"

    liquidity_state = "RESERVED"
    finalized = False
    settled_at = None
    expected_s = RAIL_INFO[rail]["expected_s"]
    jitter = max(random.lognormvariate(0, 0.3), 0.05)
    duration_s = round(expected_s * jitter, 1) if expected_s > 0 else round(jitter, 1)

    if settlement_state == "SETTLED":
        liquidity_state = "RELEASED"
        finalized = True
        settled_at = (created_at + timedelta(seconds=duration_s)).isoformat()

    payment_state = derive_payment_state(aml_state, settlement_state)

    payment = {
        "payment_id": payment_id, "uetr": uetr, "created_at": created_at.isoformat(),
        "payment_type": payment_type, "amount": amount, "currency": currency,
        "debtor_id": debtor["account_id"], "debtor_country": debtor["home_country"],
        "creditor_id": creditor["account_id"], "creditor_country": creditor_country,
        "is_cross_border": is_cross_border,
        "rail": rail, "rail_priority": RAIL_INFO[rail]["priority"], "channel": channel,
        "payment_method": payment_method,
        "fee_internal_amount": fee_internal, "fee_external_amount": fee_external,
        "aml_category_risk": category_risk, "aml_risk_score": risk_score,
        "amount_vs_account_avg": amount_vs_account_avg,
        "laundering_typology": typology, "aml_state": aml_state, "is_fraud": is_fraud,
        "liquidity_state": liquidity_state,
        "idempotency_key": idempotency_key, "idempotency_state": "NEW",
        "retry_count": 0, "retry_allowed": True, "original_payment_id": "",
        "settlement_state": settlement_state, "finalized": finalized,
        "settled_at": settled_at or "", "settlement_duration_seconds": duration_s,
        "expected_settlement_seconds": expected_s,
        "payment_state": payment_state,
        "created_at_dt": created_at,  # internal use only, stripped before CSV write
    }
    events = build_events(payment, event_id_counter)
    return payment, events


def build_events(p, counter):
    """Causal timeline for one payment. Each event carries event_id,
    parent_event_id (previous step in this payment's own chain) and
    caused_by (cross-cutting causal pointer, e.g. an AML decision causing
    a BLOCKED state) so a graph builder gets real causal edges, not
    inferred ones. service_state is kept separate from payment_state:
    almost always HEALTHY here because the base corpus is deliberately
    fault-free at the system level (see module docstring) -- FAILED only
    appears on the small share of payments with ordinary settlement
    failures, which is normal production reality, not an injected incident.
    """
    events = []
    t = p["created_at_dt"]

    def emit(service, event_type, old_state, new_state, service_state="HEALTHY", caused_by=""):
        nonlocal t
        eid = f"E-{counter[0]:08d}"
        counter[0] += 1
        parent = events[-1]["event_id"] if events else ""
        events.append({
            "event_id": eid, "payment_id": p["payment_id"], "parent_event_id": parent,
            "caused_by": caused_by, "timestamp": t.isoformat(), "service": service,
            "event_type": event_type, "old_state": old_state, "new_state": new_state,
            "service_state": service_state, "correlation_id": p["payment_id"],
            "trace_id": p["uetr"],
        })
        return eid

    emit("gateway", "STATE_TRANSITION", "", "ACCEPTED")
    t += timedelta(milliseconds=random.randint(20, 150))
    emit("gateway", "STATE_TRANSITION", "ACCEPTED", "INITIATED")
    t += timedelta(milliseconds=random.randint(30, 200))
    emit("validation-enrichment", "STATE_TRANSITION", "INITIATED", "VALIDATED")
    t += timedelta(milliseconds=random.randint(50, 400))
    aml_event = emit("aml-compliance", "AML_DECISION", "VALIDATED", "AML_SCREENED")

    if p["aml_state"] in ("HOLD", "ESCALATED", "REJECTED"):
        t += timedelta(milliseconds=random.randint(10, 50))
        emit("aml-compliance", "POLICY_HOLD", "AML_SCREENED", p["payment_state"], caused_by=aml_event)
        return events  # blocked/rejected -- chain stops here, matches settlement_state=PENDING/FAILED

    t += timedelta(milliseconds=random.randint(100, 600))
    routed_event = emit("routing-execution", "STATE_TRANSITION", "AML_SCREENED", "ROUTED")
    t += timedelta(milliseconds=random.randint(50, 300))
    liq_event = emit("routing-execution", "STATE_TRANSITION", "ROUTED", "LIQUIDITY_RESERVED", caused_by=routed_event)
    t += timedelta(milliseconds=random.randint(50, 300))
    pending_event = emit("settlement", "STATE_TRANSITION", "LIQUIDITY_RESERVED", "SETTLEMENT_PENDING")

    if p["retry_count"] > 0:
        t += timedelta(seconds=random.randint(1, 60))
        emit("gateway", "DUPLICATE_DETECTED", "SETTLEMENT_PENDING", "SETTLEMENT_PENDING",
             caused_by=pending_event)

    if p["settlement_state"] == "SETTLED":
        t += timedelta(seconds=min(p["settlement_duration_seconds"], 3600))
        settled_event = emit("settlement", "STATE_TRANSITION", "SETTLEMENT_PENDING", "SETTLED",
                              caused_by=pending_event)
        emit("routing-execution", "STATE_TRANSITION", "RESERVED", "RELEASED", caused_by=settled_event)
    elif p["settlement_state"] == "FAILED":
        t += timedelta(seconds=random.randint(5, 120))
        emit("settlement", "STATE_TRANSITION", "SETTLEMENT_PENDING", "FAILED",
             service_state="FAILED", caused_by=pending_event)
        emit("routing-execution", "COMPENSATION", "RESERVED", "RELEASED", caused_by=pending_event)
    # PENDING: chain ends in-flight, no terminal event -- deliberately, this
    # is what a "still processing" payment looks like at snapshot time.

    return events


def clone_as_duplicate(original, new_id, delay_seconds, event_id_counter):
    """Real idempotency collision: identical debtor/creditor/amount, so the
    recomputed key genuinely matches -- fixes the v1 bug where duplicate
    rows had unrelated field values but a borrowed key.
    """
    dup = dict(original)
    dup["payment_id"] = new_id
    dup["created_at_dt"] = original["created_at_dt"] + timedelta(seconds=delay_seconds)
    dup["created_at"] = dup["created_at_dt"].isoformat()
    dup["uetr"] = str(uuid.uuid4())
    dup["idempotency_state"] = "DUPLICATE_DETECTED"
    dup["retry_count"] = original["retry_count"] + 1
    dup["retry_allowed"] = original["settlement_state"] != "SETTLED"
    dup["original_payment_id"] = original["payment_id"]
    events = build_events(dup, event_id_counter)
    return dup, events


PAYMENT_FIELDS = [
    "payment_id", "uetr", "created_at", "payment_type", "amount", "currency",
    "debtor_id", "debtor_country", "creditor_id", "creditor_country", "is_cross_border",
    "rail", "rail_priority", "channel", "payment_method",
    "fee_internal_amount", "fee_external_amount",
    "aml_category_risk", "aml_risk_score", "amount_vs_account_avg",
    "laundering_typology", "aml_state", "is_fraud",
    "liquidity_state", "idempotency_key", "idempotency_state",
    "retry_count", "retry_allowed", "original_payment_id",
    "settlement_state", "finalized", "settled_at",
    "settlement_duration_seconds", "expected_settlement_seconds", "payment_state",
]
EVENT_FIELDS = [
    "event_id", "payment_id", "parent_event_id", "caused_by", "timestamp",
    "service", "event_type", "old_state", "new_state", "service_state",
    "correlation_id", "trace_id",
]
ACCOUNT_FIELDS = [
    "account_id", "account_type", "home_country", "home_currency",
    "risk_tier", "is_pep", "avg_amount",
]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    debtors = make_accounts(N_DEBTORS, "CUST")
    creditors = make_accounts(N_CREDITORS, "MERCH")
    creditors_by_currency = {c: [] for c in CURRENCY_WEIGHTS}
    for acc in creditors:
        creditors_by_currency[acc["home_currency"]].append(acc)

    event_id_counter = [0]
    n_base = int(N_PAYMENTS * 0.992)
    payments, all_events = [], []

    for i in range(n_base):
        p, evs = build_payment(i, debtors, creditors_by_currency, event_id_counter)
        payments.append(p)
        all_events.extend(evs)

    # duplicates: real clones of an earlier payment, seconds-to-minutes later
    n_dupes = N_PAYMENTS - n_base
    idx = n_base
    for _ in range(n_dupes):
        original = random.choice(payments)
        dup, evs = clone_as_duplicate(original, f"PAY-{idx:08d}", random.randint(1, 300), event_id_counter)
        payments.append(dup)
        all_events.extend(evs)
        idx += 1

    with open(f"{OUT_DIR}/accounts.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ACCOUNT_FIELDS)
        w.writeheader()
        w.writerows(debtors)
        w.writerows(creditors)

    with open(f"{OUT_DIR}/clearflow_rca_dataset.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=PAYMENT_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(payments)

    with open(f"{OUT_DIR}/payment_events.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=EVENT_FIELDS)
        w.writeheader()
        w.writerows(all_events)

    print(f"accounts.csv: {len(debtors) + len(creditors)} rows")
    print(f"clearflow_rca_dataset.csv: {len(payments)} rows")
    print(f"payment_events.csv: {len(all_events)} rows ({len(all_events)/len(payments):.2f} events/payment)")
    print(f"is_fraud rate: {sum(p['is_fraud'] for p in payments)/len(payments):.4%}")
    print(f"aml_state non-CLEAR rate: {sum(1 for p in payments if p['aml_state']!='CLEAR')/len(payments):.4%}")
    print(f"cross_border rate: {sum(1 for p in payments if p['is_cross_border'])/len(payments):.4%}")
    print(f"duplicate rate: {sum(1 for p in payments if p['idempotency_state']=='DUPLICATE_DETECTED')/len(payments):.4%}")


if __name__ == "__main__":
    main()
