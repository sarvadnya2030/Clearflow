package com.clearflow.audit.messaging;

import com.clearflow.audit.domain.AuditRecord;
import com.clearflow.audit.repository.AuditRepository;
import com.clearflow.audit.service.HashChainService;
import com.clearflow.common.idempotency.StageIdempotencyGuard;
import com.clearflow.common.messaging.KafkaTopics;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.slf4j.MDC;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.stereotype.Component;

@Component
public class AuditEventConsumer {

    private static final Logger log = LoggerFactory.getLogger(AuditEventConsumer.class);
    private static final String STAGE = "audit";

    private final HashChainService hashChainService;
    private final AuditRepository auditRepository;
    private final ObjectMapper objectMapper;
    private final StageIdempotencyGuard idempotencyGuard;
    private final Counter saveFailures;

    public AuditEventConsumer(HashChainService hashChainService,
                               AuditRepository auditRepository,
                               ObjectMapper objectMapper,
                               StageIdempotencyGuard idempotencyGuard,
                               MeterRegistry meterRegistry) {
        this.hashChainService  = hashChainService;
        this.auditRepository   = auditRepository;
        this.objectMapper      = objectMapper;
        this.idempotencyGuard  = idempotencyGuard;
        this.saveFailures      = Counter.builder("clearflow_audit_save_failures_total")
                .description("Cassandra save failures in audit consumer")
                .register(meterRegistry);
    }

    @KafkaListener(
            topics = {
                    KafkaTopics.PAYMENT_INITIATED,
                    KafkaTopics.PAYMENT_VALIDATED,
                    KafkaTopics.PAYMENT_REJECTED,
                    KafkaTopics.FRAUD_EVALUATED,
                    KafkaTopics.PAYMENT_BLOCKED,
                    KafkaTopics.AML_SANCTIONS_CLEAR,
                    KafkaTopics.AML_SANCTIONS_HIT,
                    KafkaTopics.COMPLIANCE_ALERTS,
                    KafkaTopics.PAYMENT_ROUTED,
                    KafkaTopics.PAYMENT_FAILED,
                    KafkaTopics.PAYMENT_SETTLED,
                    KafkaTopics.ANALYTICS_SETTLEMENT,
                    KafkaTopics.MCP_ACCESS_LOG
            },
            groupId = "audit-service",
            containerFactory = "auditKafkaListenerContainerFactory"
    )
    public void onEvent(ConsumerRecord<String, String> record, Acknowledgment ack) {
        String paymentId = record.key() != null ? record.key() : extractPaymentId(record.value());
        String dedupeKey = record.topic() + ":" + paymentId;
        MDC.put("paymentId", paymentId);
        String correlationId = extractField(record.value(), "correlationId");
        if (correlationId != null) MDC.put("correlationId", correlationId);
        try {
            if (idempotencyGuard.alreadyProcessed(STAGE, dedupeKey)) {
                ack.acknowledge();
                return;
            }

            AuditRecord auditRecord = hashChainService.createRecord(paymentId, record.topic(), record.value());
            try {
                auditRepository.save(auditRecord);
            } catch (Exception ex) {
                saveFailures.increment();
                log.warn("Cassandra save failed for paymentId={} topic={} — acknowledging anyway: {}",
                        paymentId, record.topic(), ex.getMessage());
            }
            ack.acknowledge();
        } finally {
            MDC.remove("paymentId");
            MDC.remove("correlationId");
        }
    }

    private String extractPaymentId(String json) {
        String val = extractField(json, "paymentId");
        return val != null ? val : "UNKNOWN";
    }

    private String extractField(String json, String field) {
        if (json == null) return null;
        try {
            JsonNode node = objectMapper.readTree(json);
            JsonNode val = node.path(field);
            return val.isMissingNode() || val.isNull() ? null : val.asText();
        } catch (Exception e) {
            return null;
        }
    }
}
