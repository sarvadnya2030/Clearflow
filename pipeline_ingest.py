#!/usr/bin/env python3
"""
ClearFlow Pipeline Integration — Generate 100K+ PaySim Transactions & Pipeline Logs
====================================================================================
This script:
  1. Generates 100,000+ realistic PaySim-style transactions
  2. Simulates the full ClearFlow pipeline (7 services)
  3. Indexes all events into Elasticsearch (per-service indices + alerts)
  4. Writes structured pipeline logs to ingestion.log + pipeline.log
  5. Injects cascading failure scenarios (~8% of transactions) simulating
     real-world microservices failure patterns: CIRCUIT_BREAKER, RETRY_STORM,
     SAGA_COMPENSATION, DOWNSTREAM_STARVATION

Pipeline stages simulated:
  gateway → fraud-scoring → validation-enrichment → aml-compliance
  → routing-execution → settlement → audit

Usage:
    python pipeline_ingest.py                  # full run
    python pipeline_ingest.py --count 10000    # custom count
    python pipeline_ingest.py --dry-run        # stats only, no ES
"""

import uuid
import random
import time
import sys
import json
import math
import logging
from datetime import datetime, date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

random.seed(42)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ES_URL         = "http://localhost:9200"
TOTAL          = 1_00_000
ES_BULK_SIZE   = 1000
WORKERS        = 16

FRAUD_RATE     = 0.05
AML_RATE       = 0.02
EMBARGO_RATE   = 0.02

SANCTIONED_NAMES  = ["GAZPROMBANK", "AL RAHMAN TARIQ", "OSAMA BIN LADEN",
                      "KIM JONG UN", "HUSSAIN AL-QAEDA", "PYONGYANG TRADING CO"]
EMBARGO_COUNTRIES = ["KP", "IR", "CU", "SY", "SD", "RU"]
NORMAL_COUNTRIES  = ["US", "GB", "DE", "FR", "NL", "CH", "JP", "AU", "CA", "SG",
                      "IE", "BE", "AT", "DK", "SE", "NO", "FI", "IT", "ES", "PT"]
CHANNELS   = ["WEB", "MOBILE", "API", "BRANCH"]
CURRENCIES = ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "CNY", "SEK", "NZD"]
PURPOSES   = ["SUPP", "INTC", "SALA", "PENS", "TAXS", "TREA", "CORT", "GDDS"]
RAILS      = ["SEPA_INSTANT", "SEPA_CREDIT_TRANSFER", "FASTER_PAYMENTS",
              "SWIFT_GPI", "SWIFT_MT103", "TARGET2", "CHAPS", "FEDWIRE", "INTERNAL"]
RISK_BANDS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

TYPE_CHOICES = ["PAYMENT", "CASH_OUT", "CASH_IN", "TRANSFER", "DEBIT"]
TYPE_PROBS   = [0.34, 0.35, 0.22, 0.08, 0.01]

FRAUD_PATTERNS = ["ACCOUNT_TAKEOVER", "VELOCITY_BURST", "ROUND_TRIP",
                  "MULE_NETWORK", "IMPOSSIBLE_GEOGRAPHY", "EMBARGOED_TRANSIT"]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_DIR = "/home/admin-/Desktop/EDI6/clearflow"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(f"{LOG_DIR}/pipeline.log", mode='w'),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger("pipeline")

# ---------------------------------------------------------------------------
# Pre-generated pools
# ---------------------------------------------------------------------------
_COMPANY_POOL = [
    f"{random.choice(['Global','Apex','Nordic','Pacific','Atlantic','Euro','Trans','Quantum','Stellar','Nova','Prime','Core','Nexus','Titan','Vertex'])} "
    f"{random.choice(['Trading','Finance','Capital','Holdings','Systems','Solutions','Partners','Industries','Group','Logistics','Energy','Tech','Media','Ventures','Dynamics'])} "
    f"{random.choice(['Ltd','GmbH','Inc','Corp','SA','AG','BV','Pty','LLC','PLC','Co','AB','AS','SRL','SpA'])}"
    for _ in range(2000)
]
_BIC_POOL = [
    f"{random.choice(['DEUT','BNPA','HSBC','BARCL','CITI','JPMO','GLDS','UBSW','CRED','SOCI'])}"
    f"{random.choice(NORMAL_COUNTRIES[:10])}{random.choice(['XX','PP','MM'])}"
    for _ in range(500)
]
def _iban():
    cc = random.choice(NORMAL_COUNTRIES[:10])
    return f"{cc}{''.join([str(random.randint(0,9)) for _ in range(20)])}"
_IBAN_POOL = [_iban() for _ in range(2000)]
_REMIT_POOL = [f"Invoice {random.randint(1000,99999)} payment" for _ in range(200)] + \
              [f"PO-{random.randint(10000,99999)} settlement" for _ in range(200)]

# ---------------------------------------------------------------------------
# Amount distributions
# ---------------------------------------------------------------------------
def _normal_amount(tx_type):
    means = {"PAYMENT": 7.5, "CASH_OUT": 8.0, "CASH_IN": 8.5, "TRANSFER": 9.0, "DEBIT": 6.5}
    return round(min(random.lognormvariate(means.get(tx_type, 7), 1.5), 10_000_000), 2)

# ---------------------------------------------------------------------------
# Transaction builder
# ---------------------------------------------------------------------------
def generate_transaction(idx):
    """Build a single transaction dict with all pipeline metadata."""
    is_fraud   = random.random() < FRAUD_RATE
    is_aml     = random.random() < AML_RATE
    is_embargo = random.random() < EMBARGO_RATE

    tx_type = random.choices(TYPE_CHOICES, weights=TYPE_PROBS, k=1)[0]
    if is_fraud:
        tx_type = random.choice(["TRANSFER", "CASH_OUT"])

    amount = round(random.lognormvariate(10.5, 1.5), 2) if is_fraud else _normal_amount(tx_type)
    payment_id = str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())

    debtor_country  = random.choice(NORMAL_COUNTRIES)
    creditor_country = random.choice(EMBARGO_COUNTRIES) if is_embargo else random.choice(NORMAL_COUNTRIES)
    debtor_name  = random.choice(_COMPANY_POOL)
    creditor_name = random.choice(SANCTIONED_NAMES) if is_aml else random.choice(_COMPANY_POOL)
    currency = random.choice(CURRENCIES)
    channel  = random.choice(CHANNELS)
    step     = (idx % 743) + 1

    # Fraud scoring
    if is_fraud:
        fraud_score = round(random.uniform(0.75, 0.99), 4)
        risk_band   = "CRITICAL" if fraud_score > 0.9 else "HIGH"
        fraud_pattern = random.choice(FRAUD_PATTERNS)
    else:
        fraud_score = round(random.uniform(0.01, 0.40), 4)
        risk_band   = "LOW" if fraud_score < 0.15 else "MEDIUM"
        fraud_pattern = None

    # AML screening
    if is_aml:
        screening_result = "HIT"
        aml_detail       = f"Sanctions match: {creditor_name}"
    else:
        screening_result = "CLEAR"
        aml_detail       = "No sanctions match"

    # Embargo
    if is_embargo:
        embargo_result = "BLOCKED"
        embargo_detail = f"Embargoed country: {creditor_country}"
    else:
        embargo_result = "CLEAR"
        embargo_detail = "Country check passed"

    # Routing
    rail = random.choice(RAILS)
    routing_ok = not (is_fraud and risk_band == "CRITICAL") and not is_embargo

    # Settlement
    settled = routing_ok and screening_result != "HIT"

    # Timestamps (spread over last 90 days)
    base_ts = datetime.utcnow() - timedelta(days=random.randint(0, 90),
                                             hours=random.randint(0, 23),
                                             minutes=random.randint(0, 59))
    ts_str = base_ts.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Balance simulation
    if is_fraud:
        old_orig, new_orig, old_dest, new_dest = round(amount, 2), 0.0, 0.0, 0.0
    else:
        old_orig = round(random.lognormvariate(10, 2), 2)
        new_orig = round(max(old_orig - amount, 0), 2)
        old_dest = round(random.lognormvariate(10, 2), 2)
        new_dest = round(old_dest + amount, 2)

    return {
        "paymentId": payment_id,
        "correlationId": correlation_id,
        "step": step,
        "txType": tx_type,
        "amount": amount,
        "currency": currency,
        "channel": channel,
        "debtorName": debtor_name,
        "debtorCountry": debtor_country,
        "debtorIban": random.choice(_IBAN_POOL),
        "debtorBic": random.choice(_BIC_POOL),
        "creditorName": creditor_name,
        "creditorCountry": creditor_country,
        "creditorIban": random.choice(_IBAN_POOL),
        "creditorBic": random.choice(_BIC_POOL),
        "purpose": random.choice(PURPOSES),
        "remittanceInfo": random.choice(_REMIT_POOL),
        "rail": rail,
        # Flags
        "isFraud": is_fraud,
        "isAml": is_aml,
        "isEmbargo": is_embargo,
        "fraudPattern": fraud_pattern or "NONE",
        # Scoring
        "fraudScore": fraud_score,
        "riskBand": risk_band,
        "screeningResult": screening_result,
        "amlDetail": aml_detail,
        "embargoResult": embargo_result,
        "embargoDetail": embargo_detail,
        # Routing / Settlement
        "routingOk": routing_ok,
        "settled": settled,
        # Balances (PaySim)
        "oldBalanceOrig": old_orig,
        "newBalanceOrig": new_orig,
        "oldBalanceDest": old_dest,
        "newBalanceDest": new_dest,
        "isFlaggedFraud": 1 if (is_fraud and amount > 200_000) else 0,
        # Timestamps
        "timestamp": ts_str,
    }

# ---------------------------------------------------------------------------
# Pipeline event builders  (mirror clearflow.conf logstash format)
# ---------------------------------------------------------------------------
def pipeline_events(tx):
    """Generate 5-7 pipeline log events for one transaction (one per service)."""
    pid = tx["paymentId"]
    ts  = tx["timestamp"]
    events = []

    def ts_offset(seconds):
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ") + timedelta(seconds=seconds)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1. Gateway — PAYMENT_SUBMITTED
    events.append({
        "@timestamp": ts,
        "paymentId": pid,
        "service": "gateway",
        "level": "INFO",
        "eventType": "PAYMENT_SUBMITTED",
        "message": f"PAYMENT_SUBMITTED paymentId={pid} debtorCountry={tx['debtorCountry']} creditorCountry={tx['creditorCountry']} amount={tx['amount']} currency={tx['currency']} channel={tx['channel']}",
        "debtorCountry": tx["debtorCountry"],
        "creditorCountry": tx["creditorCountry"],
        "currency": tx["currency"],
        "amount": tx["amount"],
        "channel": tx["channel"],
        "txType": tx["txType"],
    })

    # 2. Fraud scoring — FRAUD_SCORE_COMPUTED
    level = "WARN" if tx["riskBand"] in ("HIGH", "CRITICAL") else "INFO"
    events.append({
        "@timestamp": ts_offset(1),
        "paymentId": pid,
        "service": "fraud-scoring",
        "level": level,
        "eventType": "FRAUD_SCORE_COMPUTED",
        "message": f"FRAUD_SCORE_COMPUTED paymentId={pid} fraudScore={tx['fraudScore']} riskBand={tx['riskBand']}",
        "fraudScore": tx["fraudScore"],
        "riskBand": tx["riskBand"],
        "fraudPattern": tx["fraudPattern"],
        "modelVersion": "xgboost-paysim-v3",
        "amount": tx["amount"],
        "currency": tx["currency"],
    })

    # 3. Validation — IBAN_VALIDATED + EMBARGO_CHECK
    events.append({
        "@timestamp": ts_offset(2),
        "paymentId": pid,
        "service": "validation-enrichment",
        "level": "WARN" if tx["isEmbargo"] else "INFO",
        "eventType": "IBAN_VALIDATED",
        "message": f"IBAN_VALIDATED paymentId={pid} result=OK",
        "debtorCountry": tx["debtorCountry"],
        "creditorCountry": tx["creditorCountry"],
        "currency": tx["currency"],
    })
    events.append({
        "@timestamp": ts_offset(2),
        "paymentId": pid,
        "service": "validation-enrichment",
        "level": "ERROR" if tx["isEmbargo"] else "INFO",
        "eventType": "EMBARGO_CHECK",
        "message": f"EMBARGO_CHECK paymentId={pid} result={tx['embargoResult']} {tx['embargoDetail']}",
        "embargoResult": tx["embargoResult"],
        "creditorCountry": tx["creditorCountry"],
    })

    # 4. AML compliance — AML_SCREENING_COMPLETE or AML_SANCTIONS_HIT
    if tx["screeningResult"] == "HIT":
        events.append({
            "@timestamp": ts_offset(3),
            "paymentId": pid,
            "service": "aml-compliance",
            "level": "ERROR",
            "eventType": "AML_SANCTIONS_HIT",
            "message": f"AML_SANCTIONS_HIT paymentId={pid} {tx['amlDetail']}",
            "screeningResult": "HIT",
            "creditorName": tx["creditorName"],
            "amount": tx["amount"],
            "currency": tx["currency"],
        })
    else:
        events.append({
            "@timestamp": ts_offset(3),
            "paymentId": pid,
            "service": "aml-compliance",
            "level": "INFO",
            "eventType": "AML_SCREENING_COMPLETE",
            "message": f"AML_SCREENING_COMPLETE paymentId={pid} result=CLEAR",
            "screeningResult": "CLEAR",
            "amount": tx["amount"],
            "currency": tx["currency"],
        })

    # 5. Routing — RAIL_SELECTED (if not blocked)
    if tx["routingOk"]:
        events.append({
            "@timestamp": ts_offset(4),
            "paymentId": pid,
            "service": "routing-execution",
            "level": "INFO",
            "eventType": "RAIL_SELECTED",
            "message": f"RAIL_SELECTED paymentId={pid} rail={tx['rail']}",
            "rail": tx["rail"],
            "amount": tx["amount"],
            "currency": tx["currency"],
            "debtorCountry": tx["debtorCountry"],
            "creditorCountry": tx["creditorCountry"],
        })

    # 6. Settlement — SETTLEMENT_COMPLETE (if settled)
    if tx["settled"]:
        events.append({
            "@timestamp": ts_offset(5),
            "paymentId": pid,
            "service": "settlement",
            "level": "INFO",
            "eventType": "SETTLEMENT_COMPLETE",
            "message": f"SETTLEMENT_COMPLETE paymentId={pid} amount={tx['amount']} currency={tx['currency']} rail={tx['rail']}",
            "rail": tx["rail"],
            "amount": tx["amount"],
            "currency": tx["currency"],
        })
    elif tx["riskBand"] == "CRITICAL":
        events.append({
            "@timestamp": ts_offset(5),
            "paymentId": pid,
            "service": "settlement",
            "level": "ERROR",
            "eventType": "PAYMENT_STATUS_UPDATE",
            "message": f"PAYMENT_BLOCKED paymentId={pid} reason=FRAUD_CRITICAL fraudScore={tx['fraudScore']}",
            "riskBand": "CRITICAL",
            "amount": tx["amount"],
        })

    # 7. Audit — AUDIT_CHAIN_APPENDED (always)
    final_status = "SETTLED" if tx["settled"] else ("BLOCKED" if tx["riskBand"] == "CRITICAL" or tx["isEmbargo"] else "REJECTED")
    events.append({
        "@timestamp": ts_offset(6),
        "paymentId": pid,
        "service": "audit",
        "level": "INFO",
        "eventType": "AUDIT_CHAIN_APPENDED",
        "message": f"AUDIT_CHAIN_APPENDED paymentId={pid} status={final_status}",
        "finalStatus": final_status,
        "amount": tx["amount"],
        "currency": tx["currency"],
    })

    return events

# ---------------------------------------------------------------------------
# Cascading failure scenarios  (real-world microservices failure patterns)
# ---------------------------------------------------------------------------
CASCADE_RATE = 0.08  # 8% of transactions get cascade events in addition to normal

CASCADE_TYPES = ["CIRCUIT_BREAKER", "RETRY_STORM", "SAGA_COMPENSATION", "DOWNSTREAM_STARVATION"]

def cascade_events(tx):
    """
    Generate additional cascading failure log events that show multi-service failures.
    These simulate real-world patterns:
      CIRCUIT_BREAKER     — fraud-scoring times out → circuit opens → gateway queued
      RETRY_STORM         — validation fails → gateway retries flood → dead letter queue
      SAGA_COMPENSATION   — settlement fails → saga unwinds all upstream reservations
      DOWNSTREAM_STARVATION — settlement DB pool exhausted → routing → gateway all impacted
    """
    pid = tx["paymentId"]
    ts = tx["timestamp"]
    events = []

    def ts_offset(seconds):
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ") + timedelta(seconds=seconds)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    cascade_type = random.choice(CASCADE_TYPES)

    if cascade_type == "CIRCUIT_BREAKER":
        # fraud-scoring times out 3x → circuit opens → gateway falls back → payment queued
        for attempt in range(1, 4):
            events.append({
                "@timestamp": ts_offset(attempt),
                "paymentId": pid, "service": "fraud-scoring",
                "level": "WARN", "eventType": "SERVICE_TIMEOUT",
                "message": f"SERVICE_TIMEOUT paymentId={pid} attempt={attempt}/3 elapsed=5001ms threshold=5000ms",
                "attempt": attempt, "thresholdMs": 5000, "elapsedMs": 5000 + attempt * 100,
                "cascadeType": "CIRCUIT_BREAKER",
            })
        events.append({
            "@timestamp": ts_offset(4),
            "paymentId": pid, "service": "fraud-scoring",
            "level": "ERROR", "eventType": "CIRCUIT_BREAKER_OPEN",
            "message": f"CIRCUIT_BREAKER_OPEN service=fraud-scoring after 3 consecutive timeouts — fallback activated",
            "circuitState": "OPEN", "consecutiveFailures": 3, "recoveryWindowSec": 30,
            "cascadeType": "CIRCUIT_BREAKER",
        })
        events.append({
            "@timestamp": ts_offset(5),
            "paymentId": pid, "service": "gateway",
            "level": "WARN", "eventType": "CIRCUIT_BREAKER_FALLBACK",
            "message": f"CIRCUIT_BREAKER_FALLBACK paymentId={pid} fraud-scoring unavailable — defaulting score=0.5 riskBand=MEDIUM",
            "fallbackScore": 0.5, "fallbackRiskBand": "MEDIUM",
            "cascadeType": "CIRCUIT_BREAKER",
        })
        events.append({
            "@timestamp": ts_offset(6),
            "paymentId": pid, "service": "gateway",
            "level": "WARN", "eventType": "PAYMENT_QUEUED",
            "message": f"PAYMENT_QUEUED paymentId={pid} reason=CIRCUIT_OPEN downstream=fraud-scoring queueDepth=47",
            "queueDepth": 47, "reason": "CIRCUIT_OPEN", "cascadeType": "CIRCUIT_BREAKER",
        })

    elif cascade_type == "RETRY_STORM":
        # validation BIC lookup times out → gateway retries 3x → DLQ
        events.append({
            "@timestamp": ts_offset(1),
            "paymentId": pid, "service": "validation-enrichment",
            "level": "WARN", "eventType": "EXTERNAL_LOOKUP_TIMEOUT",
            "message": f"EXTERNAL_LOOKUP_TIMEOUT paymentId={pid} service=BIC_REGISTRY elapsed=3002ms",
            "externalService": "BIC_REGISTRY", "elapsedMs": 3002, "cascadeType": "RETRY_STORM",
        })
        for attempt in range(1, 4):
            events.append({
                "@timestamp": ts_offset(attempt + 2),
                "paymentId": pid, "service": "gateway",
                "level": "WARN", "eventType": "PAYMENT_RETRY",
                "message": f"PAYMENT_RETRY paymentId={pid} attempt={attempt}/3 delay={attempt*2}s reason=VALIDATION_TIMEOUT",
                "attempt": attempt, "delaySeconds": attempt * 2,
                "cascadeType": "RETRY_STORM",
            })
        events.append({
            "@timestamp": ts_offset(10),
            "paymentId": pid, "service": "gateway",
            "level": "ERROR", "eventType": "DEAD_LETTER_QUEUE",
            "message": f"DEAD_LETTER_QUEUE paymentId={pid} exhausted 3 retries — moved to DLQ topic=clearflow.payments.dlq",
            "dlqTopic": "clearflow.payments.dlq", "totalAttempts": 3, "finalReason": "MAX_RETRIES_EXCEEDED",
            "cascadeType": "RETRY_STORM",
        })
        events.append({
            "@timestamp": ts_offset(10),
            "paymentId": pid, "service": "validation-enrichment",
            "level": "ERROR", "eventType": "QUEUE_OVERFLOW_WARNING",
            "message": f"QUEUE_OVERFLOW_WARNING retry traffic elevated pendingMessages=523 threshold=500",
            "pendingMessages": 523, "threshold": 500, "cascadeType": "RETRY_STORM",
        })
        events.append({
            "@timestamp": ts_offset(11),
            "paymentId": pid, "service": "audit",
            "level": "INFO", "eventType": "AUDIT_CHAIN_APPENDED",
            "message": f"AUDIT_CHAIN_APPENDED paymentId={pid} status=DLQ",
            "finalStatus": "DLQ", "cascadeType": "RETRY_STORM",
        })

    elif cascade_type == "SAGA_COMPENSATION":
        # settlement DB fails → saga unwinds routing reservation → AML releases hold → audit records
        events.append({
            "@timestamp": ts_offset(5),
            "paymentId": pid, "service": "settlement",
            "level": "ERROR", "eventType": "SETTLEMENT_TIMEOUT",
            "message": f"SETTLEMENT_TIMEOUT paymentId={pid} DB connection pool exhausted connections=50/50 waitMs=30000",
            "dbConnections": "50/50", "waitMs": 30000, "cascadeType": "SAGA_COMPENSATION",
        })
        events.append({
            "@timestamp": ts_offset(6),
            "paymentId": pid, "service": "settlement",
            "level": "ERROR", "eventType": "SAGA_COMPENSATION_STARTED",
            "message": f"SAGA_COMPENSATION_STARTED paymentId={pid} initiating rollback across all upstream stages",
            "sagaId": f"SAGA-{pid[:8]}", "compensationStages": 4, "cascadeType": "SAGA_COMPENSATION",
        })
        events.append({
            "@timestamp": ts_offset(7),
            "paymentId": pid, "service": "routing-execution",
            "level": "WARN", "eventType": "ROUTING_RESERVATION_RELEASED",
            "message": f"ROUTING_RESERVATION_RELEASED paymentId={pid} rail=SEPA_INSTANT reservation cancelled",
            "sagaStep": "1/4", "cascadeType": "SAGA_COMPENSATION",
        })
        events.append({
            "@timestamp": ts_offset(8),
            "paymentId": pid, "service": "aml-compliance",
            "level": "WARN", "eventType": "AML_HOLD_RELEASED",
            "message": f"AML_HOLD_RELEASED paymentId={pid} compliance hold removed due to saga rollback",
            "sagaStep": "2/4", "cascadeType": "SAGA_COMPENSATION",
        })
        events.append({
            "@timestamp": ts_offset(9),
            "paymentId": pid, "service": "fraud-scoring",
            "level": "INFO", "eventType": "FRAUD_RESERVATION_VOIDED",
            "message": f"FRAUD_RESERVATION_VOIDED paymentId={pid} fraud check voided — saga rollback",
            "sagaStep": "3/4", "cascadeType": "SAGA_COMPENSATION",
        })
        events.append({
            "@timestamp": ts_offset(10),
            "paymentId": pid, "service": "gateway",
            "level": "WARN", "eventType": "PAYMENT_COMPENSATED",
            "message": f"PAYMENT_COMPENSATED paymentId={pid} saga complete — payment rolled back to submitted state",
            "sagaStep": "4/4", "finalStatus": "COMPENSATED", "cascadeType": "SAGA_COMPENSATION",
        })
        events.append({
            "@timestamp": ts_offset(11),
            "paymentId": pid, "service": "audit",
            "level": "INFO", "eventType": "AUDIT_CHAIN_APPENDED",
            "message": f"AUDIT_CHAIN_APPENDED paymentId={pid} status=COMPENSATED sagaId=SAGA-{pid[:8]}",
            "finalStatus": "COMPENSATED", "cascadeType": "SAGA_COMPENSATION",
        })

    elif cascade_type == "DOWNSTREAM_STARVATION":
        # settlement DB pool full → routing ACK times out → gateway sees unknown state → ops alert
        events.append({
            "@timestamp": ts_offset(5),
            "paymentId": pid, "service": "settlement",
            "level": "ERROR", "eventType": "DB_CONNECTION_POOL_EXHAUSTED",
            "message": f"DB_CONNECTION_POOL_EXHAUSTED pool=settlement-db active=50 pending=23 maxWait=30000ms",
            "activeConnections": 50, "pendingRequests": 23, "maxWaitMs": 30000,
            "cascadeType": "DOWNSTREAM_STARVATION",
        })
        events.append({
            "@timestamp": ts_offset(6),
            "paymentId": pid, "service": "routing-execution",
            "level": "ERROR", "eventType": "SETTLEMENT_ACK_TIMEOUT",
            "message": f"SETTLEMENT_ACK_TIMEOUT paymentId={pid} no acknowledgment from settlement in 10000ms",
            "timeoutMs": 10000, "cascadeType": "DOWNSTREAM_STARVATION",
        })
        events.append({
            "@timestamp": ts_offset(7),
            "paymentId": pid, "service": "routing-execution",
            "level": "ERROR", "eventType": "PAYMENT_STUCK",
            "message": f"PAYMENT_STUCK paymentId={pid} routed but settlement unresponsive — escalating to ops",
            "escalatedToOps": True, "cascadeType": "DOWNSTREAM_STARVATION",
        })
        events.append({
            "@timestamp": ts_offset(8),
            "paymentId": pid, "service": "gateway",
            "level": "WARN", "eventType": "PAYMENT_STATUS_UNKNOWN",
            "message": f"PAYMENT_STATUS_UNKNOWN paymentId={pid} no terminal status received — manual review required",
            "requiresManualReview": True, "cascadeType": "DOWNSTREAM_STARVATION",
        })
        events.append({
            "@timestamp": ts_offset(9),
            "paymentId": pid, "service": "gateway",
            "level": "WARN", "eventType": "BACKPRESSURE_APPLIED",
            "message": f"BACKPRESSURE_APPLIED reducing ingest rate from 500tps to 100tps — settlement degraded",
            "previousTps": 500, "newTps": 100, "reason": "SETTLEMENT_DEGRADED",
            "cascadeType": "DOWNSTREAM_STARVATION",
        })
        events.append({
            "@timestamp": ts_offset(10),
            "paymentId": pid, "service": "audit",
            "level": "WARN", "eventType": "AUDIT_CHAIN_APPENDED",
            "message": f"AUDIT_CHAIN_APPENDED paymentId={pid} status=UNKNOWN_MANUAL_REVIEW",
            "finalStatus": "UNKNOWN_MANUAL_REVIEW", "cascadeType": "DOWNSTREAM_STARVATION",
        })

    return events

# ---------------------------------------------------------------------------
# ES index mapping  (matches clearflow.conf output sections)
# ---------------------------------------------------------------------------
SERVICE_INDEX_MAP = {
    "gateway":                "clearflow-gateway",
    "fraud-scoring":          "clearflow-fraud",
    "validation-enrichment":  "clearflow-validation",
    "aml-compliance":         "clearflow-aml",
    "routing-execution":      "clearflow-routing",
    "settlement":             "clearflow-settlement",
    "audit":                  "clearflow-audit",
}

def es_index_for(event):
    base = SERVICE_INDEX_MAP.get(event["service"], f"clearflow-{event['service']}")
    ts = event.get("@timestamp", "")[:10].replace("-", ".")
    return f"{base}-{ts}"

def alert_level(event):
    if event.get("level") == "ERROR" or event.get("riskBand") == "CRITICAL" or \
       event.get("screeningResult") == "HIT" or "BLOCKED" in event.get("message", "") or \
       "CRITICAL" in event.get("message", "") or "SANCTIONS_HIT" in event.get("message", ""):
        return "HIGH"
    if event.get("level") == "WARN" or event.get("riskBand") == "HIGH":
        return "MEDIUM"
    return "LOW"

# ---------------------------------------------------------------------------
# ES bulk indexer  (using urllib to avoid aiohttp/requests dependency)
# ---------------------------------------------------------------------------
import urllib.request, urllib.error

def es_bulk_index(events, dry_run=False):
    """Bulk-index a batch of events into Elasticsearch."""
    if dry_run or not events:
        return len(events), 0

    lines = []
    alert_lines = []
    for ev in events:
        idx = es_index_for(ev)
        ev["alertLevel"] = alert_level(ev)
        ev["environment"] = "clearflow"
        meta = json.dumps({"index": {"_index": idx}})
        doc  = json.dumps(ev)
        lines.append(meta)
        lines.append(doc)
        # HIGH alerts → alerts index too
        if ev["alertLevel"] == "HIGH":
            ts = ev.get("@timestamp", "")[:10].replace("-", ".")
            alert_meta = json.dumps({"index": {"_index": f"clearflow-alerts-{ts}"}})
            alert_lines.append(alert_meta)
            alert_lines.append(doc)

    body = "\n".join(lines) + "\n"
    if alert_lines:
        body += "\n".join(alert_lines) + "\n"

    req = urllib.request.Request(
        f"{ES_URL}/_bulk",
        data=body.encode("utf-8"),
        headers={"Content-Type": "application/x-ndjson"},
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        result = json.loads(resp.read())
        errors = sum(1 for item in result.get("items", []) if item.get("index", {}).get("error"))
        return len(events), errors
    except Exception as e:
        log.warning(f"ES bulk index error: {e}")
        return len(events), len(events)

# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def main():
    # Parse args
    dry_run = "--dry-run" in sys.argv
    count = TOTAL
    for i, arg in enumerate(sys.argv):
        if arg == "--count" and i + 1 < len(sys.argv):
            count = int(sys.argv[i + 1])

    log.info("=" * 70)
    log.info("  ClearFlow Pipeline Integration — PaySim Transaction Simulator")
    log.info("=" * 70)
    log.info(f"  Transactions  : {count:,}")
    log.info(f"  Fraud rate    : {FRAUD_RATE*100:.1f}%")
    log.info(f"  AML rate      : {AML_RATE*100:.1f}%")
    log.info(f"  Embargo rate  : {EMBARGO_RATE*100:.1f}%")
    log.info(f"  ES endpoint   : {ES_URL}")
    log.info(f"  Mode          : {'DRY-RUN' if dry_run else 'LIVE → Elasticsearch'}")
    log.info("=" * 70)

    # ── Step 1: Generate transactions ────────────────────────────────────────
    log.info("⏳ Phase 1/3: Generating transactions …")
    t0 = time.time()
    transactions = [generate_transaction(i) for i in range(count)]
    gen_time = time.time() - t0
    log.info(f"✅ Generated {len(transactions):,} transactions in {gen_time:.1f}s")

    # Stats
    n_fraud   = sum(1 for tx in transactions if tx["isFraud"])
    n_aml     = sum(1 for tx in transactions if tx["isAml"])
    n_embargo = sum(1 for tx in transactions if tx["isEmbargo"])
    n_settled = sum(1 for tx in transactions if tx["settled"])
    n_blocked = sum(1 for tx in transactions if tx["riskBand"] == "CRITICAL")
    types_ct  = {}
    patterns_ct = {}
    bands_ct = {}
    for tx in transactions:
        types_ct[tx["txType"]] = types_ct.get(tx["txType"], 0) + 1
        bands_ct[tx["riskBand"]] = bands_ct.get(tx["riskBand"], 0) + 1
        if tx["fraudPattern"]:
            patterns_ct[tx["fraudPattern"]] = patterns_ct.get(tx["fraudPattern"], 0) + 1

    log.info(f"📊 Transaction Breakdown:")
    log.info(f"   Total      : {len(transactions):,}")
    log.info(f"   Fraud      : {n_fraud:,}  ({n_fraud/len(transactions)*100:.2f}%)")
    log.info(f"   AML-hit    : {n_aml:,}")
    log.info(f"   Embargo    : {n_embargo:,}")
    log.info(f"   Settled    : {n_settled:,}")
    log.info(f"   Blocked    : {n_blocked:,}")
    for t in sorted(types_ct):
        log.info(f"   {t:15s}: {types_ct[t]:>6,}  ({types_ct[t]/len(transactions)*100:.1f}%)")
    log.info(f"🚨 Risk Bands:")
    for b in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]:
        log.info(f"   {b:10s}: {bands_ct.get(b,0):>6,}")
    if patterns_ct:
        log.info(f"🔍 Fraud Patterns:")
        for p in sorted(patterns_ct):
            log.info(f"   {p:25s}: {patterns_ct[p]:>4,}")

    # ── Step 2: Generate pipeline events ─────────────────────────────────────
    log.info("\n⏳ Phase 2/3: Generating pipeline events …")
    t1 = time.time()
    all_events = []
    cascade_count = 0
    for tx in transactions:
        all_events.extend(pipeline_events(tx))
        if random.random() < CASCADE_RATE:
            cascade_events_list = cascade_events(tx)
            all_events.extend(cascade_events_list)
            cascade_count += 1
    pipe_time = time.time() - t1
    log.info(f"✅ Generated {len(all_events):,} pipeline events in {pipe_time:.1f}s ({cascade_count:,} cascade scenarios injected)")

    # Events per service
    svc_counts = {}
    alert_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for ev in all_events:
        svc_counts[ev["service"]] = svc_counts.get(ev["service"], 0) + 1
        al = alert_level(ev)
        alert_counts[al] += 1

    log.info("📋 Events per service:")
    for s in sorted(svc_counts):
        log.info(f"   {s:25s}: {svc_counts[s]:>7,}")
    log.info(f"🚨 Alert levels:  HIGH={alert_counts['HIGH']:,}  MEDIUM={alert_counts['MEDIUM']:,}  LOW={alert_counts['LOW']:,}")

    # ── Step 3: Index into Elasticsearch ─────────────────────────────────────
    log.info(f"\n⏳ Phase 3/3: Indexing {len(all_events):,} events into Elasticsearch …")
    t2 = time.time()
    total_indexed = 0
    total_errors  = 0

    for batch_start in range(0, len(all_events), ES_BULK_SIZE):
        batch = all_events[batch_start:batch_start + ES_BULK_SIZE]
        indexed, errors = es_bulk_index(batch, dry_run=dry_run)
        total_indexed += indexed
        total_errors  += errors
        if (batch_start // ES_BULK_SIZE + 1) % 20 == 0 or batch_start + ES_BULK_SIZE >= len(all_events):
            elapsed = time.time() - t2
            rate = total_indexed / elapsed if elapsed > 0 else 0
            log.info(f"   Indexed {total_indexed:,}/{len(all_events):,}  ({rate:,.0f} events/sec)  errors={total_errors}")

    idx_time = time.time() - t2
    total_time = time.time() - t0

    log.info(f"\n{'='*70}")
    log.info(f"✅ Pipeline complete!")
    log.info(f"   Transactions generated : {len(transactions):,}")
    log.info(f"   Pipeline events        : {len(all_events):,}")
    log.info(f"   Indexed to ES          : {total_indexed:,}")
    log.info(f"   Index errors           : {total_errors}")
    log.info(f"   Generation time        : {gen_time:.1f}s")
    log.info(f"   Pipeline event time    : {pipe_time:.1f}s")
    log.info(f"   ES indexing time       : {idx_time:.1f}s")
    log.info(f"   Total time             : {total_time:.1f}s")
    log.info(f"{'='*70}")

    # ── Write ingestion log ──────────────────────────────────────────────────
    with open(f"{LOG_DIR}/ingestion.log", "a") as f:
        f.write(f"\n--- Pipeline run @ {datetime.now().isoformat()} ---\n")
        f.write(f"Transactions: {len(transactions):,}\n")
        f.write(f"Pipeline events: {len(all_events):,}\n")
        f.write(f"Fraud: {n_fraud:,} ({n_fraud/len(transactions)*100:.2f}%)\n")
        f.write(f"AML hits: {n_aml:,}\n")
        f.write(f"Embargo: {n_embargo:,}\n")
        f.write(f"Settled: {n_settled:,}\n")
        f.write(f"Blocked: {n_blocked:,}\n")
        f.write(f"ES indexed: {total_indexed:,} (errors: {total_errors})\n")
        f.write(f"Total time: {total_time:.1f}s\n")

    log.info(f"\n📁 Logs written to:")
    log.info(f"   {LOG_DIR}/pipeline.log")
    log.info(f"   {LOG_DIR}/ingestion.log")

    if not dry_run:
        log.info(f"\n🔍 View in Kibana: http://localhost:5601")
        log.info(f"   Index patterns: clearflow-gateway-*, clearflow-fraud-*, clearflow-aml-*, etc.")
        log.info(f"   Alerts index:   clearflow-alerts-*")

if __name__ == "__main__":
    main()
