package com.clearflow.audit.config;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.ExponentialBackOff;

@Configuration
public class AuditKafkaErrorHandler {

    private static final Logger log = LoggerFactory.getLogger(AuditKafkaErrorHandler.class);
    private static final String DLQ_TOPIC = "clearflow.audit.dlq";

    @Bean
    public DefaultErrorHandler auditErrorHandler(
            KafkaTemplate<String, String> kafkaTemplate,
            MeterRegistry meterRegistry) {

        Counter dlqCounter = Counter.builder("clearflow_audit_dlq_total")
                .description("Audit events routed to DLQ after max retries")
                .register(meterRegistry);
        Counter saveFailureCounter = Counter.builder("clearflow_audit_save_failures_total")
                .description("Cassandra save failures in audit consumer")
                .register(meterRegistry);

        // Exponential back-off: 1s → 2s → 4s → … up to 30s, max 3 attempts
        ExponentialBackOff backOff = new ExponentialBackOff(1_000L, 2.0);
        backOff.setMaxInterval(30_000L);
        backOff.setMaxAttempts(3);

        DefaultErrorHandler handler = new DefaultErrorHandler((record, exception) -> {
            // Terminal handler — called after all retries exhausted
            saveFailureCounter.increment();
            String key   = String.valueOf(record.key());
            String value = String.valueOf(record.value());
            String topic = record.topic();

            log.warn("Audit event sent to DLQ after retries exhausted: topic={} key={} cause={}",
                    topic, key, exception.getMessage());
            dlqCounter.increment();

            try {
                kafkaTemplate.send(DLQ_TOPIC, key, value);
            } catch (Exception dlqEx) {
                log.error("Failed to write to audit DLQ — event may be lost: key={}", key, dlqEx);
            }
        }, backOff);

        // Do not retry on deserialization errors (they will never succeed)
        handler.addNotRetryableExceptions(org.springframework.kafka.support.serializer.DeserializationException.class);

        return handler;
    }
}
