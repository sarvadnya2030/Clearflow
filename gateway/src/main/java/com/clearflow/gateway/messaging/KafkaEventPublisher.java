package com.clearflow.gateway.messaging;

import com.clearflow.common.domain.PaymentInitiatedEvent;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component
public class KafkaEventPublisher {

    private static final Logger log = LoggerFactory.getLogger(KafkaEventPublisher.class);
    private static final String OUTBOX_KEY = "outbox:pending";

    private final StringRedisTemplate redis;
    private final ObjectMapper objectMapper;

    public KafkaEventPublisher(StringRedisTemplate redis, ObjectMapper objectMapper) {
        this.redis        = redis;
        this.objectMapper = objectMapper;
    }

    public void publish(PaymentInitiatedEvent event, String traceParent, String traceState) {
        PaymentOutboxEntry entry = new PaymentOutboxEntry(
                event.paymentId(), traceParent, traceState, event, 0);
        try {
            String json = objectMapper.writeValueAsString(entry);
            redis.opsForList().leftPush(OUTBOX_KEY, json);
            log.info("Outbox enqueued paymentId={}", event.paymentId());
        } catch (Exception ex) {
            log.error("Outbox enqueue failed paymentId={}", event.paymentId(), ex);
            throw new RuntimeException("Outbox enqueue failed for paymentId=" + event.paymentId(), ex);
        }
    }
}
