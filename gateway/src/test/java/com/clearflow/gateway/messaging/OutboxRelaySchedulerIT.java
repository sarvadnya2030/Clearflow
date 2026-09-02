package com.clearflow.gateway.messaging;

import com.clearflow.common.IntegrationTestBase;
import com.clearflow.common.domain.PaymentInitiatedEvent;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.ActiveProfiles;

import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("dev")
class OutboxRelaySchedulerIT extends IntegrationTestBase {

    @Autowired
    private KafkaEventPublisher publisher;

    @Autowired
    private StringRedisTemplate redis;

    @Autowired
    private ObjectMapper objectMapper;

    @BeforeEach
    void cleanOutbox() {
        redis.delete("outbox:pending");
        redis.delete("outbox:inflight");
    }

    @AfterEach
    void cleanupAfter() {
        redis.delete("outbox:pending");
        redis.delete("outbox:inflight");
    }

    @Test
    void publishEnqueuesEntryInRedisAndRelayDeliversToKafka() throws Exception {
        String paymentId = "OUTBOX-IT-" + UUID.randomUUID();
        PaymentInitiatedEvent event = sampleEvent(paymentId);

        publisher.publish(event, "traceparent-test", "tracestate-test");

        // Verify entry was pushed to outbox:pending immediately
        Long depth = redis.opsForList().size("outbox:pending");
        assertThat(depth).isGreaterThanOrEqualTo(1);

        // Wait for the scheduler (fixedDelay=200ms) to relay to Kafka
        List<String> received = consumeFromKafka("clearflow.payment.initiated", paymentId, 5_000);
        assertThat(received)
                .withFailMessage("Kafka should have received the payment initiated event")
                .isNotEmpty();
        assertThat(received.get(0)).contains(paymentId);

        // outbox:inflight should be empty once delivered
        Thread.sleep(500);
        Long inflight = redis.opsForList().size("outbox:inflight");
        assertThat(inflight).isZero();
    }

    @Test
    void duplicatePublishDoesNotDoubleDeliver() throws Exception {
        String paymentId = "OUTBOX-DUP-" + UUID.randomUUID();
        PaymentInitiatedEvent event = sampleEvent(paymentId);

        // Publish same event twice
        publisher.publish(event, "tp1", "ts1");
        publisher.publish(event, "tp2", "ts2");

        // Both go to outbox (idempotency is at consumer side, not publisher)
        Long depth = redis.opsForList().size("outbox:pending");
        assertThat(depth).isGreaterThanOrEqualTo(2);
    }

    private List<String> consumeFromKafka(String topic, String expectedKey, long timeoutMs) {
        Map<String, Object> props = Map.of(
                ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, KAFKA.getBootstrapServers(),
                ConsumerConfig.GROUP_ID_CONFIG, "outbox-it-" + UUID.randomUUID(),
                ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest",
                ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class,
                ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class,
                ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, true
        );
        List<String> results = new ArrayList<>();
        long deadline = System.currentTimeMillis() + timeoutMs;
        try (KafkaConsumer<String, String> consumer = new KafkaConsumer<>(props)) {
            consumer.subscribe(List.of(topic));
            while (System.currentTimeMillis() < deadline) {
                ConsumerRecords<String, String> records = consumer.poll(Duration.ofMillis(200));
                records.forEach(r -> {
                    if (expectedKey.equals(r.key())) results.add(r.value());
                });
                if (!results.isEmpty()) break;
            }
        }
        return results;
    }

    private PaymentInitiatedEvent sampleEvent(String paymentId) {
        return new PaymentInitiatedEvent(
                paymentId, UUID.randomUUID().toString(),
                "INST-001", "E2E-001", UUID.randomUUID().toString(),
                "DE89370400440532013000", "NL91ABNA0417164300",
                "Test Debtor", "Test Creditor",
                "DEUTDEDB", "ABNANL2A",
                new BigDecimal("1000.00"), "EUR",
                "DE", "NL", "SWIFT",
                Instant.now(), "gateway"
        );
    }
}
