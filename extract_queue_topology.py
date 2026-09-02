#!/usr/bin/env python3
"""
extract_queue_topology.py
Reads ClearFlow Java source files to validate/enrich the broker topology
and writes a comprehensive JSON structure to graphify-out/queue_topology.json.
"""

import os
import re
import json
import datetime
from pathlib import Path

BASE_DIR = Path("/home/admin-/Desktop/EDI6/clearflow")
OUT_DIR  = BASE_DIR / "graphify-out"
OUT_FILE = OUT_DIR / "queue_topology.json"

# ── Pattern matchers ──────────────────────────────────────────────────────────

def grep_java(pattern: str, root: Path) -> list[dict]:
    """Grep all .java files under root for pattern; return list of {file, line, text}."""
    results = []
    for java_file in sorted(root.rglob("*.java")):
        try:
            text = java_file.read_text(errors="replace")
            for i, line in enumerate(text.splitlines(), 1):
                if re.search(pattern, line):
                    results.append({
                        "file": str(java_file.relative_to(BASE_DIR)),
                        "line": i,
                        "text": line.strip(),
                    })
        except Exception:
            pass
    return results


def derive_service(file_path: str) -> str:
    """Extract the leading module directory as service name."""
    parts = file_path.split("/")
    return parts[0] if parts else "unknown"


def derive_class(file_path: str) -> str:
    """Extract class name from file path."""
    return Path(file_path).stem


def collect_kafka_producers() -> list[dict]:
    """Find kafkaTemplate.send() and from/to kafka: in Camel routes."""
    hits = grep_java(r'kafkaTemplate\.send|to\("kafka:', BASE_DIR)
    producers = []
    for h in hits:
        svc = derive_service(h["file"])
        cls = derive_class(h["file"])
        # Try to extract topic name from the line
        m = re.search(r'"(clearflow\.[^"]+)"', h["text"])
        topic = m.group(1) if m else None
        producers.append({"service": svc, "class": cls, "file": h["file"], "topic": topic, "raw": h["text"]})
    return producers


def collect_kafka_consumers() -> list[dict]:
    """Find @KafkaListener and from("kafka: in Camel routes."""
    hits = grep_java(r'@KafkaListener|from\("kafka:', BASE_DIR)
    consumers = []
    for h in hits:
        svc = derive_service(h["file"])
        cls = derive_class(h["file"])
        # topics can appear as topics = {"..."} or in from("kafka:topic")
        topics = re.findall(r'"(clearflow\.[^"]+)"', h["text"])
        consumers.append({"service": svc, "class": cls, "file": h["file"], "topics": topics, "raw": h["text"]})
    return consumers


def collect_activemq_producers() -> list[dict]:
    """Find to("jms:queue: patterns."""
    hits = grep_java(r'to\("jms:queue:', BASE_DIR)
    producers = []
    for h in hits:
        svc = derive_service(h["file"])
        cls = derive_class(h["file"])
        m = re.search(r'to\("jms:queue:([A-Z0-9_.]+)"', h["text"])
        queue = m.group(1) if m else None
        producers.append({"service": svc, "class": cls, "file": h["file"], "queue": queue, "raw": h["text"]})
    return producers


def collect_activemq_consumers() -> list[dict]:
    """Find from("jms:queue: patterns."""
    hits = grep_java(r'from\("jms:queue:', BASE_DIR)
    consumers = []
    for h in hits:
        svc = derive_service(h["file"])
        cls = derive_class(h["file"])
        m = re.search(r'from\("jms:queue:([A-Z0-9_.]+)"', h["text"])
        queue = m.group(1) if m else None
        consumers.append({"service": svc, "class": cls, "file": h["file"], "queue": queue, "raw": h["text"]})
    return consumers


# ── Static topology definition (from user-provided analysis) ─────────────────

KAFKA_TOPICS = {
    "clearflow.payment.initiated": {
        "purpose": "Payment submitted by client — triggers fraud scoring and audit fan-out",
        "isDLQ": False,
        "isSagaTrigger": False,
        "producers": [
            {"service": "gateway", "class": "KafkaEventPublisher",
             "file": "gateway/src/main/java/com/clearflow/gateway/messaging/KafkaEventPublisher.java"},
        ],
        "consumers": [
            {"service": "fraud-scoring",  "class": "FraudKafkaConsumer",
             "file": "fraud-scoring/src/main/java/com/clearflow/fraud/messaging/FraudKafkaConsumer.java"},
            {"service": "audit",          "class": "AuditEventConsumer",
             "file": "audit/src/main/java/com/clearflow/audit/messaging/AuditEventConsumer.java"},
            {"service": "gateway",        "class": "PaymentStatusKafkaConsumer",
             "file": "gateway/src/main/java/com/clearflow/gateway/status/PaymentStatusKafkaConsumer.java"},
        ],
    },
    "clearflow.fraud.evaluated": {
        "purpose": "Fraud risk score and band published after ML evaluation",
        "isDLQ": False,
        "isSagaTrigger": False,
        "producers": [
            {"service": "fraud-scoring", "class": "FraudKafkaConsumer",
             "file": "fraud-scoring/src/main/java/com/clearflow/fraud/messaging/FraudKafkaConsumer.java"},
        ],
        "consumers": [
            {"service": "audit", "class": "AuditEventConsumer",
             "file": "audit/src/main/java/com/clearflow/audit/messaging/AuditEventConsumer.java"},
        ],
    },
    "clearflow.payment.blocked": {
        "purpose": "Payment blocked by fraud engine (CRITICAL risk band) — no further processing",
        "isDLQ": False,
        "isSagaTrigger": False,
        "producers": [
            {"service": "fraud-scoring", "class": "FraudKafkaConsumer",
             "file": "fraud-scoring/src/main/java/com/clearflow/fraud/messaging/FraudKafkaConsumer.java"},
        ],
        "consumers": [
            {"service": "audit",   "class": "AuditEventConsumer",
             "file": "audit/src/main/java/com/clearflow/audit/messaging/AuditEventConsumer.java"},
            {"service": "gateway", "class": "PaymentStatusKafkaConsumer",
             "file": "gateway/src/main/java/com/clearflow/gateway/status/PaymentStatusKafkaConsumer.java"},
        ],
    },
    "clearflow.payment.validated": {
        "purpose": "Payment passed schema/IBAN/BIC validation and enrichment",
        "isDLQ": False,
        "isSagaTrigger": False,
        "producers": [
            {"service": "validation-enrichment", "class": "ValidationEnrichmentCamelRoute",
             "file": "validation-enrichment/src/main/java/com/clearflow/validation/camel/ValidationEnrichmentCamelRoute.java"},
        ],
        "consumers": [
            {"service": "audit",   "class": "AuditEventConsumer",
             "file": "audit/src/main/java/com/clearflow/audit/messaging/AuditEventConsumer.java"},
            {"service": "gateway", "class": "PaymentStatusKafkaConsumer",
             "file": "gateway/src/main/java/com/clearflow/gateway/status/PaymentStatusKafkaConsumer.java"},
        ],
    },
    "clearflow.payment.rejected": {
        "purpose": "Payment failed validation (invalid IBAN, BIC, schema, or amount) — terminal",
        "isDLQ": False,
        "isSagaTrigger": False,
        "producers": [
            {"service": "validation-enrichment", "class": "ValidationEnrichmentCamelRoute",
             "file": "validation-enrichment/src/main/java/com/clearflow/validation/camel/ValidationEnrichmentCamelRoute.java"},
        ],
        "consumers": [
            {"service": "audit",   "class": "AuditEventConsumer",
             "file": "audit/src/main/java/com/clearflow/audit/messaging/AuditEventConsumer.java"},
            {"service": "gateway", "class": "PaymentStatusKafkaConsumer",
             "file": "gateway/src/main/java/com/clearflow/gateway/status/PaymentStatusKafkaConsumer.java"},
        ],
    },
    "clearflow.aml.sanctions.hit": {
        "purpose": "AML screening matched OFAC/SDN/PEP list — payment held for compliance review",
        "isDLQ": False,
        "isSagaTrigger": False,
        "producers": [
            {"service": "aml-compliance", "class": "AMLCamelRoute",
             "file": "aml-compliance/src/main/java/com/clearflow/compliance/camel/AMLCamelRoute.java"},
        ],
        "consumers": [
            {"service": "audit",   "class": "AuditEventConsumer",
             "file": "audit/src/main/java/com/clearflow/audit/messaging/AuditEventConsumer.java"},
            {"service": "gateway", "class": "PaymentStatusKafkaConsumer",
             "file": "gateway/src/main/java/com/clearflow/gateway/status/PaymentStatusKafkaConsumer.java"},
        ],
    },
    "clearflow.aml.sanctions.clear": {
        "purpose": "AML screening passed — payment cleared for routing and execution",
        "isDLQ": False,
        "isSagaTrigger": False,
        "producers": [
            {"service": "aml-compliance", "class": "AMLCamelRoute",
             "file": "aml-compliance/src/main/java/com/clearflow/compliance/camel/AMLCamelRoute.java"},
        ],
        "consumers": [
            {"service": "audit",   "class": "AuditEventConsumer",
             "file": "audit/src/main/java/com/clearflow/audit/messaging/AuditEventConsumer.java"},
            {"service": "gateway", "class": "PaymentStatusKafkaConsumer",
             "file": "gateway/src/main/java/com/clearflow/gateway/status/PaymentStatusKafkaConsumer.java"},
        ],
    },
    "clearflow.compliance.alerts": {
        "purpose": "High-priority compliance alert (embargo country, sanctions, PEP) for operations team",
        "isDLQ": False,
        "isSagaTrigger": False,
        "producers": [
            {"service": "aml-compliance", "class": "AMLCamelRoute",
             "file": "aml-compliance/src/main/java/com/clearflow/compliance/camel/AMLCamelRoute.java"},
        ],
        "consumers": [
            {"service": "audit", "class": "AuditEventConsumer",
             "file": "audit/src/main/java/com/clearflow/audit/messaging/AuditEventConsumer.java"},
        ],
    },
    "clearflow.payment.routed": {
        "purpose": "Payment assigned to rail (SWIFT/SEPA/TARGET2/RTP) and execution confirmed",
        "isDLQ": False,
        "isSagaTrigger": False,
        "producers": [
            {"service": "routing-execution", "class": "RoutingCamelRoute",
             "file": "routing-execution/src/main/java/com/clearflow/routing/camel/RoutingCamelRoute.java"},
        ],
        "consumers": [
            {"service": "audit",   "class": "AuditEventConsumer",
             "file": "audit/src/main/java/com/clearflow/audit/messaging/AuditEventConsumer.java"},
            {"service": "gateway", "class": "PaymentStatusKafkaConsumer",
             "file": "gateway/src/main/java/com/clearflow/gateway/status/PaymentStatusKafkaConsumer.java"},
        ],
    },
    "clearflow.payment.failed": {
        "purpose": "Routing or execution failed (liquidity, rail unavailable, timeout) — saga may trigger",
        "isDLQ": False,
        "isSagaTrigger": False,
        "producers": [
            {"service": "routing-execution", "class": "RoutingCamelRoute",
             "file": "routing-execution/src/main/java/com/clearflow/routing/camel/RoutingCamelRoute.java"},
        ],
        "consumers": [
            {"service": "audit",   "class": "AuditEventConsumer",
             "file": "audit/src/main/java/com/clearflow/audit/messaging/AuditEventConsumer.java"},
            {"service": "gateway", "class": "PaymentStatusKafkaConsumer",
             "file": "gateway/src/main/java/com/clearflow/gateway/status/PaymentStatusKafkaConsumer.java"},
        ],
    },
    "clearflow.payment.settled": {
        "purpose": "Payment fully settled — funds confirmed in nostro account",
        "isDLQ": False,
        "isSagaTrigger": False,
        "producers": [
            {"service": "settlement", "class": "SettlementCamelRoute",
             "file": "settlement/src/main/java/com/clearflow/settlement/camel/SettlementCamelRoute.java"},
        ],
        "consumers": [
            {"service": "audit",   "class": "AuditEventConsumer",
             "file": "audit/src/main/java/com/clearflow/audit/messaging/AuditEventConsumer.java"},
            {"service": "gateway", "class": "PaymentStatusKafkaConsumer",
             "file": "gateway/src/main/java/com/clearflow/gateway/status/PaymentStatusKafkaConsumer.java"},
        ],
    },
    "clearflow.analytics.settlement": {
        "purpose": "Settlement analytics event for external data warehouse / reporting pipeline",
        "isDLQ": False,
        "isSagaTrigger": False,
        "producers": [
            {"service": "settlement", "class": "SettlementCamelRoute",
             "file": "settlement/src/main/java/com/clearflow/settlement/camel/SettlementCamelRoute.java"},
        ],
        "consumers": [],  # external analytics consumer outside ClearFlow boundary
    },
    "clearflow.mcp.access.log": {
        "purpose": "MCP read-only gateway access log for audit trail of AI tool queries",
        "isDLQ": False,
        "isSagaTrigger": False,
        "producers": [
            {"service": "mcp-readonly-gateway", "class": "AccessLogService",
             "file": "mcp-readonly-gateway/src/main/java/com/clearflow/mcp/service/AccessLogService.java"},
        ],
        "consumers": [
            {"service": "audit", "class": "AuditEventConsumer",
             "file": "audit/src/main/java/com/clearflow/audit/messaging/AuditEventConsumer.java"},
        ],
    },
    "clearflow.payment.dlq": {
        "purpose": "Dead letter queue for undeliverable payment Kafka messages after max retries",
        "isDLQ": True,
        "isSagaTrigger": False,
        "producers": [],
        "consumers": [],
    },
    "clearflow.fraud.dlq": {
        "purpose": "Dead letter queue for undeliverable fraud evaluation Kafka messages after max retries",
        "isDLQ": True,
        "isSagaTrigger": False,
        "producers": [],
        "consumers": [],
    },
    "clearflow.payment.settlement.failed": {
        "purpose": "Settlement failed after nostro debit — triggers saga compensation to reverse routing/AML/fraud holds",
        "isDLQ": False,
        "isSagaTrigger": True,
        "producers": [
            {"service": "settlement", "class": "SettlementCamelRoute",
             "file": "settlement/src/main/java/com/clearflow/settlement/camel/SettlementCamelRoute.java"},
        ],
        "consumers": [
            {"service": "routing-execution", "class": "SagaCompensationRoute",
             "file": "routing-execution/src/main/java/com/clearflow/routing/camel/SagaCompensationRoute.java"},
        ],
    },
    "clearflow.payment.compensated": {
        "purpose": "Saga compensation complete — all distributed holds released, payment fully reversed",
        "isDLQ": False,
        "isSagaTrigger": False,
        "producers": [
            {"service": "routing-execution", "class": "SagaCompensationRoute",
             "file": "routing-execution/src/main/java/com/clearflow/routing/camel/SagaCompensationRoute.java"},
        ],
        "consumers": [
            {"service": "audit", "class": "AuditEventConsumer",
             "file": "audit/src/main/java/com/clearflow/audit/messaging/AuditEventConsumer.java"},
        ],
    },
}

ACTIVEMQ_QUEUES = {
    "CLEARFLOW.PAYMENT.INITIATED": {
        "purpose": "Orchestration backbone — gateway posts initiated payment, validation-enrichment picks up for Camel pipeline",
        "isDLQ": False,
        "producers": [
            {"service": "gateway", "class": "ActiveMQPublisher",
             "file": "gateway/src/main/java/com/clearflow/gateway/messaging/ActiveMQPublisher.java"},
        ],
        "consumers": [
            {"service": "validation-enrichment", "class": "ValidationEnrichmentCamelRoute",
             "file": "validation-enrichment/src/main/java/com/clearflow/validation/camel/ValidationEnrichmentCamelRoute.java"},
        ],
    },
    "CLEARFLOW.PAYMENT.VALIDATED": {
        "purpose": "Validated + enriched payment handed off to AML compliance screening",
        "isDLQ": False,
        "producers": [
            {"service": "validation-enrichment", "class": "ValidationEnrichmentCamelRoute",
             "file": "validation-enrichment/src/main/java/com/clearflow/validation/camel/ValidationEnrichmentCamelRoute.java"},
        ],
        "consumers": [
            {"service": "aml-compliance", "class": "AMLCamelRoute",
             "file": "aml-compliance/src/main/java/com/clearflow/compliance/camel/AMLCamelRoute.java"},
        ],
    },
    "CLEARFLOW.PAYMENT.REJECTED": {
        "purpose": "Validation-rejected payment — terminal queue, no active consumer (goes to DLQ audit trail)",
        "isDLQ": False,
        "producers": [
            {"service": "validation-enrichment", "class": "ValidationEnrichmentCamelRoute",
             "file": "validation-enrichment/src/main/java/com/clearflow/validation/camel/ValidationEnrichmentCamelRoute.java"},
        ],
        "consumers": [],  # terminal — DLQ audit
    },
    "CLEARFLOW.PAYMENT.SANCTIONS.HIT": {
        "purpose": "Sanctions match — payment put on compliance hold, terminal queue awaiting manual review",
        "isDLQ": False,
        "producers": [
            {"service": "aml-compliance", "class": "AMLCamelRoute",
             "file": "aml-compliance/src/main/java/com/clearflow/compliance/camel/AMLCamelRoute.java"},
        ],
        "consumers": [],  # terminal — compliance hold
    },
    "CLEARFLOW.PAYMENT.SANCTIONS.CLEAR": {
        "purpose": "AML cleared — payment routed onward to routing-execution for rail selection",
        "isDLQ": False,
        "producers": [
            {"service": "aml-compliance", "class": "AMLCamelRoute",
             "file": "aml-compliance/src/main/java/com/clearflow/compliance/camel/AMLCamelRoute.java"},
        ],
        "consumers": [
            {"service": "routing-execution", "class": "RoutingCamelRoute",
             "file": "routing-execution/src/main/java/com/clearflow/routing/camel/RoutingCamelRoute.java"},
        ],
    },
    "CLEARFLOW.PAYMENT.ROUTED": {
        "purpose": "Rail selected and execution confirmed — settlement service picks up for nostro debit",
        "isDLQ": False,
        "producers": [
            {"service": "routing-execution", "class": "RoutingCamelRoute",
             "file": "routing-execution/src/main/java/com/clearflow/routing/camel/RoutingCamelRoute.java"},
        ],
        "consumers": [
            {"service": "settlement", "class": "SettlementCamelRoute",
             "file": "settlement/src/main/java/com/clearflow/settlement/camel/SettlementCamelRoute.java"},
        ],
    },
    "CLEARFLOW.PAYMENT.SETTLED": {
        "purpose": "Settlement confirmed — terminal queue, consumed by audit trail processor",
        "isDLQ": False,
        "producers": [
            {"service": "settlement", "class": "SettlementCamelRoute",
             "file": "settlement/src/main/java/com/clearflow/settlement/camel/SettlementCamelRoute.java"},
        ],
        "consumers": [],  # terminal — audit trail
    },
    "CLEARFLOW.PAYMENT.DLQ": {
        "purpose": "Dead letter queue for all Camel pipeline failures — 3 retries + exponential backoff exhausted",
        "isDLQ": True,
        "producers": [],  # all Camel error handlers route here
        "consumers": [],
    },
    "CLEARFLOW.PAYMENT.INSUFFICIENT.LIQUIDITY": {
        "purpose": "Routing failed due to insufficient liquidity on selected rail — triggers manual intervention",
        "isDLQ": False,
        "producers": [
            {"service": "routing-execution", "class": "RoutingCamelRoute",
             "file": "routing-execution/src/main/java/com/clearflow/routing/camel/RoutingCamelRoute.java"},
        ],
        "consumers": [],
    },
    "CLEARFLOW.PAYMENT.SETTLEMENT.FAILED": {
        "purpose": "Settlement failure after nostro debit — consumed by SagaCompensationRoute to orchestrate distributed rollback",
        "isDLQ": False,
        "producers": [
            {"service": "settlement", "class": "SettlementCamelRoute",
             "file": "settlement/src/main/java/com/clearflow/settlement/camel/SettlementCamelRoute.java"},
        ],
        "consumers": [
            {"service": "routing-execution", "class": "SagaCompensationRoute",
             "file": "routing-execution/src/main/java/com/clearflow/routing/camel/SagaCompensationRoute.java"},
        ],
    },
    "CLEARFLOW.PAYMENT.COMPENSATED": {
        "purpose": "Saga compensation complete — produced by SagaCompensationRoute, marks end of distributed rollback",
        "isDLQ": False,
        "producers": [
            {"service": "routing-execution", "class": "SagaCompensationRoute",
             "file": "routing-execution/src/main/java/com/clearflow/routing/camel/SagaCompensationRoute.java"},
        ],
        "consumers": [],
    },
}

# ── Enrich from Java source ───────────────────────────────────────────────────

def enrich_from_source(kafka_topics: dict, activemq_queues: dict) -> dict:
    """
    Actually grep the Java source and annotate each topic/queue with
    validated_producers and validated_consumers lists.
    Returns a summary of what was found.
    """
    print("Scanning Java source files...")

    kafka_producers_found  = collect_kafka_producers()
    kafka_consumers_found  = collect_kafka_consumers()
    activemq_producers_found = collect_activemq_producers()
    activemq_consumers_found = collect_activemq_consumers()

    summary = {
        "kafka_producer_hits": len(kafka_producers_found),
        "kafka_consumer_hits": len(kafka_consumers_found),
        "activemq_producer_hits": len(activemq_producers_found),
        "activemq_consumer_hits": len(activemq_consumers_found),
    }

    # Annotate Kafka topics with source-validated evidence
    for topic_name, topic_data in kafka_topics.items():
        validated_producers = [
            p for p in kafka_producers_found
            if p.get("topic") == topic_name or topic_name in p.get("raw", "")
        ]
        validated_consumers = [
            c for c in kafka_consumers_found
            if topic_name in " ".join(c.get("topics", [])) or topic_name in c.get("raw", "")
        ]
        topic_data["sourceValidation"] = {
            "producerHits": [{"file": p["file"], "line": p["line"]} for p in validated_producers],
            "consumerHits": [{"file": c["file"], "line": c["line"]} for c in validated_consumers],
        }

    # Annotate ActiveMQ queues with source-validated evidence
    for queue_name, queue_data in activemq_queues.items():
        validated_producers = [
            p for p in activemq_producers_found
            if p.get("queue") == queue_name or queue_name in p.get("raw", "")
        ]
        validated_consumers = [
            c for c in activemq_consumers_found
            if c.get("queue") == queue_name or queue_name in c.get("raw", "")
        ]
        queue_data["sourceValidation"] = {
            "producerHits": [{"file": p["file"], "line": p["line"]} for p in validated_producers],
            "consumerHits": [{"file": c["file"], "line": c["line"]} for c in validated_consumers],
        }

    print(f"  Kafka producer matches: {summary['kafka_producer_hits']}")
    print(f"  Kafka consumer matches: {summary['kafka_consumer_hits']}")
    print(f"  ActiveMQ producer matches: {summary['activemq_producer_hits']}")
    print(f"  ActiveMQ consumer matches: {summary['activemq_consumer_hits']}")
    return summary


# ── Build topology JSON ───────────────────────────────────────────────────────

def build_topology() -> dict:
    enrich_from_source(KAFKA_TOPICS, ACTIVEMQ_QUEUES)

    topology = {
        "version": "1.0",
        "extractedAt": datetime.datetime.utcnow().isoformat() + "Z",
        "brokers": {
            "kafka": {
                "bootstrapServers": "kafka:9092",
                "topics": KAFKA_TOPICS,
            },
            "activemq": {
                "brokerUrl": "tcp://activemq:61616",
                "queues": ACTIVEMQ_QUEUES,
            },
            "solace": {
                "topics": {
                    "clearflow/payments/initiated/{currency}/{country}": {
                        "purpose": "Dynamic Solace hierarchical routing for regional payment handling — "
                                   "currency and country are substituted at runtime for selective consumer matching",
                        "producers": [
                            {
                                "service": "gateway",
                                "class": "SolacePublisher",
                                "file": "gateway/src/main/java/com/clearflow/gateway/messaging/SolacePublisher.java",
                            }
                        ],
                        "consumers": [],
                    }
                }
            },
        },
        "pipelineFlow": [
            {
                "step": 1,
                "service": "gateway",
                "action": "Receive ISO-20022 payment instruction from client",
                "produces": "clearflow.payment.initiated (Kafka) + CLEARFLOW.PAYMENT.INITIATED (ActiveMQ) + clearflow/payments/initiated/{currency}/{country} (Solace)",
                "via": "KafkaEventPublisher + ActiveMQPublisher + SolacePublisher",
                "circuitBreakers": ["KAFKA", "ACTIVEMQ", "SOLACE"],
            },
            {
                "step": 2,
                "service": "validation-enrichment",
                "action": "Schema validation, IBAN/BIC check, FX enrichment via Camel",
                "consumes": "CLEARFLOW.PAYMENT.INITIATED (ActiveMQ)",
                "produces": "CLEARFLOW.PAYMENT.VALIDATED or CLEARFLOW.PAYMENT.REJECTED (ActiveMQ) + clearflow.payment.validated or clearflow.payment.rejected (Kafka)",
                "via": "ValidationEnrichmentCamelRoute",
                "onError": "CLEARFLOW.PAYMENT.DLQ after 3 retries + exponential backoff",
            },
            {
                "step": 3,
                "service": "fraud-scoring",
                "action": "ML fraud scoring (RandomForest + velocity/pattern rules)",
                "consumes": "clearflow.payment.initiated (Kafka)",
                "produces": "clearflow.fraud.evaluated + clearflow.payment.blocked (if CRITICAL) (Kafka)",
                "via": "FraudKafkaConsumer",
                "onError": "clearflow.fraud.dlq after max retries",
            },
            {
                "step": 4,
                "service": "aml-compliance",
                "action": "OFAC/SDN/PEP fuzzy screening, embargo country check via Camel",
                "consumes": "CLEARFLOW.PAYMENT.VALIDATED (ActiveMQ)",
                "produces": "CLEARFLOW.PAYMENT.SANCTIONS.HIT or CLEARFLOW.PAYMENT.SANCTIONS.CLEAR (ActiveMQ) + clearflow.aml.sanctions.hit/clear + clearflow.compliance.alerts (Kafka)",
                "via": "AMLCamelRoute",
                "onError": "CLEARFLOW.PAYMENT.DLQ after 3 retries + exponential backoff",
            },
            {
                "step": 5,
                "service": "routing-execution",
                "action": "Rail selection (SWIFT/SEPA/TARGET2/RTP), liquidity check, execution",
                "consumes": "CLEARFLOW.PAYMENT.SANCTIONS.CLEAR (ActiveMQ)",
                "produces": "CLEARFLOW.PAYMENT.ROUTED or CLEARFLOW.PAYMENT.INSUFFICIENT.LIQUIDITY (ActiveMQ) + clearflow.payment.routed or clearflow.payment.failed (Kafka)",
                "via": "RoutingCamelRoute",
                "onError": "CLEARFLOW.PAYMENT.DLQ after 3 retries + exponential backoff",
            },
            {
                "step": 6,
                "service": "settlement",
                "action": "Nostro debit, settlement ACK, analytics event",
                "consumes": "CLEARFLOW.PAYMENT.ROUTED (ActiveMQ)",
                "produces": "CLEARFLOW.PAYMENT.SETTLED or CLEARFLOW.PAYMENT.SETTLEMENT.FAILED (ActiveMQ) + clearflow.payment.settled + clearflow.analytics.settlement + clearflow.payment.settlement.failed (Kafka)",
                "via": "SettlementCamelRoute",
                "onError": "CLEARFLOW.PAYMENT.DLQ after 3 retries + exponential backoff",
            },
            {
                "step": "6b",
                "service": "routing-execution",
                "action": "SAGA COMPENSATION — reverse routing reservation, release AML hold, void fraud reservation",
                "trigger": "CLEARFLOW.PAYMENT.SETTLEMENT.FAILED (ActiveMQ) + clearflow.payment.settlement.failed (Kafka)",
                "produces": "CLEARFLOW.PAYMENT.COMPENSATED (ActiveMQ) + clearflow.payment.compensated (Kafka)",
                "via": "SagaCompensationRoute",
            },
            {
                "step": 7,
                "service": "audit",
                "action": "Immutable event log — consumes ALL Kafka topics for audit trail",
                "consumes": "ALL Kafka topics (fan-in)",
                "via": "AuditEventConsumer",
            },
            {
                "step": 8,
                "service": "mcp-readonly-gateway",
                "action": "AI observability — tool queries logged to Kafka for audit",
                "produces": "clearflow.mcp.access.log (Kafka)",
                "via": "AccessLogService",
            },
        ],
        "circuitBreakers": [
            {
                "name": "KAFKA",
                "wraps": "KafkaEventPublisher",
                "service": "gateway",
                "file": "gateway/src/main/java/com/clearflow/gateway/messaging/KafkaEventPublisher.java",
                "fallback": "Routes to ActiveMQ when Kafka broker is unreachable",
                "config": "Resilience4j — default sliding window 10, failure threshold 50%, wait 30s",
            },
            {
                "name": "ACTIVEMQ",
                "wraps": "ActiveMQPublisher",
                "service": "gateway",
                "file": "gateway/src/main/java/com/clearflow/gateway/messaging/ActiveMQPublisher.java",
                "fallback": "Payment queued locally or rejected with 503",
                "config": "Resilience4j — default sliding window 10, failure threshold 50%, wait 30s",
            },
            {
                "name": "SOLACE",
                "wraps": "SolacePublisher",
                "service": "gateway",
                "file": "gateway/src/main/java/com/clearflow/gateway/messaging/SolacePublisher.java",
                "fallback": "Regional routing skipped, falls back to Kafka fan-out",
                "config": "Resilience4j — default sliding window 10, failure threshold 50%, wait 30s",
            },
        ],
        "sagaFlow": {
            "trigger": "CLEARFLOW.PAYMENT.SETTLEMENT.FAILED (ActiveMQ) + clearflow.payment.settlement.failed (Kafka)",
            "compensationRoute": "routing-execution/SagaCompensationRoute",
            "compensationRouteFile": "routing-execution/src/main/java/com/clearflow/routing/camel/SagaCompensationRoute.java",
            "steps": [
                "1. Receive settlement failure event from SettlementCamelRoute",
                "2. Release routing reservation — reverse rail assignment in RoutingCamelRoute",
                "3. Release AML hold — unblock payment in AMLCamelRoute state store",
                "4. Void fraud reservation — clear fraud engine hold in FraudKafkaConsumer",
                "5. Publish clearflow.payment.compensated (Kafka) + CLEARFLOW.PAYMENT.COMPENSATED (ActiveMQ)",
                "6. AuditEventConsumer logs full saga compensation trail",
            ],
            "idempotencyGuard": "Each compensation step checks saga-state before executing to prevent double-rollback",
        },
        "dlqConfig": {
            "maximumRedeliveries": 3,
            "redeliveryDelay": "1s",
            "backoff": "exponential",
            "backoffMultiplier": 2.0,
            "maxRedeliveryDelay": "30s",
            "dlqDestination": "jms:queue:CLEARFLOW.PAYMENT.DLQ",
            "kafkaDlqTopics": ["clearflow.payment.dlq", "clearflow.fraud.dlq"],
            "appliesTo": "ALL Apache Camel routes (ValidationEnrichmentCamelRoute, AMLCamelRoute, RoutingCamelRoute, SettlementCamelRoute, SagaCompensationRoute)",
        },
        "serviceToQueuesIndex": _build_service_index(),
    }

    return topology


def _build_service_index() -> dict:
    """Build service → [topics/queues it uses] reverse index for fast lookup."""
    index: dict[str, list] = {}

    for topic, data in KAFKA_TOPICS.items():
        for p in data.get("producers", []):
            svc = p["service"]
            index.setdefault(svc, [])
            entry = {"broker": "KAFKA", "name": topic, "role": "producer", "class": p["class"]}
            if entry not in index[svc]:
                index[svc].append(entry)
        for c in data.get("consumers", []):
            svc = c["service"]
            index.setdefault(svc, [])
            entry = {"broker": "KAFKA", "name": topic, "role": "consumer", "class": c["class"]}
            if entry not in index[svc]:
                index[svc].append(entry)

    for queue, data in ACTIVEMQ_QUEUES.items():
        for p in data.get("producers", []):
            svc = p["service"]
            index.setdefault(svc, [])
            entry = {"broker": "ACTIVEMQ", "name": queue, "role": "producer", "class": p["class"]}
            if entry not in index[svc]:
                index[svc].append(entry)
        for c in data.get("consumers", []):
            svc = c["service"]
            index.setdefault(svc, [])
            entry = {"broker": "ACTIVEMQ", "name": queue, "role": "consumer", "class": c["class"]}
            if entry not in index[svc]:
                index[svc].append(entry)

    return index


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Building ClearFlow broker topology...")
    topology = build_topology()

    with open(OUT_FILE, "w") as f:
        json.dump(topology, f, indent=2)

    print(f"\nWrote {OUT_FILE}")

    # Print first 30 lines for verification
    print("\n--- First 30 lines of queue_topology.json ---")
    with open(OUT_FILE) as f:
        for i, line in enumerate(f, 1):
            if i > 30:
                break
            print(f"{i:3d}  {line}", end="")

    # Summary stats
    kafka_count   = len(topology["brokers"]["kafka"]["topics"])
    activemq_count = len(topology["brokers"]["activemq"]["queues"])
    solace_count  = len(topology["brokers"]["solace"]["topics"])
    print(f"\n\nSummary: {kafka_count} Kafka topics, {activemq_count} ActiveMQ queues, {solace_count} Solace topic")
    print(f"         {len(topology['circuitBreakers'])} circuit breakers, {len(topology['pipelineFlow'])} pipeline steps")


if __name__ == "__main__":
    main()
