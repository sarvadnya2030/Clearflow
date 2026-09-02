package com.clearflow.gateway.messaging;

import com.clearflow.common.messaging.KafkaTopics;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.util.concurrent.TimeUnit;

@Component
public class OutboxRelayScheduler {

    private static final Logger log = LoggerFactory.getLogger(OutboxRelayScheduler.class);
    private static final String PENDING  = "outbox:pending";
    private static final String INFLIGHT = "outbox:inflight";
    private static final String DLQ_TOPIC = "clearflow.payments.dlq";
    private static final int MAX_ATTEMPTS = 5;

    private final StringRedisTemplate redis;
    private final KafkaTemplate<String, String> kafkaTemplate;
    private final ObjectMapper objectMapper;
    private final Counter relayedCounter;
    private final Counter dlqCounter;

    public OutboxRelayScheduler(StringRedisTemplate redis,
                                 @org.springframework.beans.factory.annotation.Qualifier("stringKafkaTemplate")
                                 KafkaTemplate<String, String> kafkaTemplate,
                                 ObjectMapper objectMapper,
                                 MeterRegistry meterRegistry) {
        this.redis         = redis;
        this.kafkaTemplate = kafkaTemplate;
        this.objectMapper  = objectMapper;
        this.relayedCounter = Counter.builder("clearflow_outbox_relayed_total")
                .description("Outbox entries successfully relayed to Kafka")
                .register(meterRegistry);
        this.dlqCounter = Counter.builder("clearflow_outbox_dlq_total")
                .description("Outbox entries routed to DLQ after max retries")
                .register(meterRegistry);
    }

    private static final int MAX_PER_CYCLE = 100;

    @Scheduled(fixedDelay = 200)
    public void relay() {
        String raw;
        int processed = 0;
        while (processed < MAX_PER_CYCLE && (raw = redis.opsForList().rightPopAndLeftPush(PENDING, INFLIGHT)) != null) {
            process(raw);
            processed++;
        }
    }

    private void process(String raw) {
        PaymentOutboxEntry entry;
        try {
            entry = objectMapper.readValue(raw, PaymentOutboxEntry.class);
        } catch (Exception ex) {
            log.error("Undeserializable outbox entry — dropping: {}", ex.getMessage());
            redis.opsForList().remove(INFLIGHT, 1, raw);
            return;
        }

        try {
            String eventJson = objectMapper.writeValueAsString(entry.event());
            Message<String> message = MessageBuilder.withPayload(eventJson)
                    .setHeader(KafkaHeaders.TOPIC, KafkaTopics.PAYMENT_INITIATED)
                    .setHeader(KafkaHeaders.KEY, entry.paymentId())
                    .setHeader("traceparent", entry.traceParent() != null ? entry.traceParent() : "")
                    .setHeader("tracestate", entry.traceState() != null ? entry.traceState() : "")
                    .build();
            kafkaTemplate.send(message).get(5, TimeUnit.SECONDS);
            redis.opsForList().remove(INFLIGHT, 1, raw);
            relayedCounter.increment();
            log.debug("Outbox relayed paymentId={}", entry.paymentId());

        } catch (Exception ex) {
            redis.opsForList().remove(INFLIGHT, 1, raw);

            if (entry.attempts() >= MAX_ATTEMPTS - 1) {
                dlqCounter.increment();
                log.error("Outbox max retries exhausted — routing to DLQ paymentId={}", entry.paymentId());
                try {
                    kafkaTemplate.send(DLQ_TOPIC, entry.paymentId(), raw);
                } catch (Exception dlqEx) {
                    log.error("DLQ send failed for paymentId={} — entry lost", entry.paymentId(), dlqEx);
                }
            } else {
                try {
                    String retryJson = objectMapper.writeValueAsString(entry.withAttempt());
                    redis.opsForList().leftPush(PENDING, retryJson);
                } catch (Exception serEx) {
                    log.error("Re-queue serialization failed for paymentId={} — entry lost", entry.paymentId(), serEx);
                }
                log.warn("Outbox relay failed attempt={} paymentId={}: {}",
                        entry.attempts() + 1, entry.paymentId(), ex.getMessage());
            }
        }
    }
}
