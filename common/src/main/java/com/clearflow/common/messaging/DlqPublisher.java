package com.clearflow.common.messaging;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;

import java.time.Instant;

/**
 * Reusable DLQ publisher. Routes a failed record to {@code <originalTopic>.dlq}
 * with diagnostic headers that make the failure self-describing.
 */
@Component
public class DlqPublisher {

    private static final Logger log = LoggerFactory.getLogger(DlqPublisher.class);

    private final KafkaTemplate<String, String> kafkaTemplate;
    private final Counter dlqCounter;

    public DlqPublisher(KafkaTemplate<String, String> kafkaTemplate,
                        MeterRegistry meterRegistry) {
        this.kafkaTemplate = kafkaTemplate;
        this.dlqCounter = Counter.builder("clearflow_dlq_published_total")
                .description("Records routed to any DLQ topic")
                .register(meterRegistry);
    }

    /**
     * Publish {@code payload} to {@code originalTopic + ".dlq"}.
     *
     * @param originalTopic topic the message was originally consumed from
     * @param key           message key (paymentId or similar)
     * @param payload       raw string payload of the failed message
     * @param attemptCount  number of delivery attempts made before giving up
     * @param cause         the terminal exception
     */
    public void publish(String originalTopic, String key, String payload,
                        int attemptCount, Throwable cause) {
        String dlqTopic = originalTopic + ".dlq";
        try {
            Message<String> message = MessageBuilder.withPayload(payload)
                    .setHeader(KafkaHeaders.TOPIC, dlqTopic)
                    .setHeader(KafkaHeaders.KEY, key)
                    .setHeader("x-original-topic", originalTopic)
                    .setHeader("x-failure-reason", cause != null ? truncate(cause.getMessage(), 500) : "unknown")
                    .setHeader("x-attempt-count", String.valueOf(attemptCount))
                    .setHeader("x-failed-at", Instant.now().toString())
                    .build();
            kafkaTemplate.send(message);
            dlqCounter.increment();
            log.warn("DLQ published key={} originalTopic={} attempts={} reason={}",
                    key, originalTopic, attemptCount, cause != null ? cause.getMessage() : "unknown");
        } catch (Exception dlqEx) {
            log.error("DLQ publish FAILED for key={} originalTopic={} — record lost", key, originalTopic, dlqEx);
        }
    }

    private static String truncate(String s, int max) {
        if (s == null) return "";
        return s.length() <= max ? s : s.substring(0, max);
    }
}
