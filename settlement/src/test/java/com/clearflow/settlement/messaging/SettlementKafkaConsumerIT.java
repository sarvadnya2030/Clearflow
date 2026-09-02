package com.clearflow.settlement.messaging;

import com.clearflow.common.IntegrationTestBase;
import com.clearflow.common.messaging.KafkaTopics;
import com.clearflow.settlement.repository.SettlementRepository;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import java.time.Duration;
import java.util.*;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("dev")
class SettlementKafkaConsumerIT extends IntegrationTestBase {

    @Autowired
    private SettlementRepository settlementRepository;

    @Test
    void paymentRoutedLeadsToSettlementRecord() throws Exception {
        String paymentId = "SETTLE-IT-" + UUID.randomUUID();
        String eventJson = buildRoutedEventJson(paymentId);

        try (KafkaProducer<String, String> producer = buildProducer()) {
            producer.send(new ProducerRecord<>(KafkaTopics.PAYMENT_ROUTED, paymentId, eventJson))
                    .get(5, TimeUnit.SECONDS);
        }

        // Wait for consumer to process (32 workers, should be fast)
        awaitSettlement(paymentId, 10_000);

        assertThat(settlementRepository.findByPaymentId(paymentId))
                .isPresent()
                .hasValueSatisfying(record -> {
                    assertThat(record.getStatus()).isEqualTo("SETTLED");
                    assertThat(record.getAmount()).isNotNull();
                });
    }

    @Test
    void duplicateRoutedEventResultsInExactlyOneSettlementRecord() throws Exception {
        String paymentId = "SETTLE-DUP-" + UUID.randomUUID();
        String eventJson = buildRoutedEventJson(paymentId);

        try (KafkaProducer<String, String> producer = buildProducer()) {
            // Send identical event twice
            producer.send(new ProducerRecord<>(KafkaTopics.PAYMENT_ROUTED, paymentId, eventJson)).get(5, TimeUnit.SECONDS);
            producer.send(new ProducerRecord<>(KafkaTopics.PAYMENT_ROUTED, paymentId, eventJson)).get(5, TimeUnit.SECONDS);
        }

        awaitSettlement(paymentId, 10_000);

        // Should be exactly one record despite two messages
        long count = settlementRepository.findAll().stream()
                .filter(r -> paymentId.equals(r.getPaymentId()))
                .count();
        assertThat(count)
                .withFailMessage("Idempotency guard should produce exactly 1 settlement for duplicate messages, got %d", count)
                .isEqualTo(1);
    }

    @Test
    void settledEventIsPublishedToKafka() throws Exception {
        String paymentId = "SETTLE-PUB-" + UUID.randomUUID();

        try (KafkaProducer<String, String> producer = buildProducer()) {
            producer.send(new ProducerRecord<>(KafkaTopics.PAYMENT_ROUTED, paymentId, buildRoutedEventJson(paymentId)))
                    .get(5, TimeUnit.SECONDS);
        }

        List<String> settled = consumeFromKafka(KafkaTopics.PAYMENT_SETTLED, paymentId, 10_000);
        assertThat(settled)
                .withFailMessage("PAYMENT_SETTLED topic should have received message for paymentId=%s", paymentId)
                .isNotEmpty();
        assertThat(settled.get(0)).contains(paymentId);
    }

    private void awaitSettlement(String paymentId, long timeoutMs) throws InterruptedException {
        long deadline = System.currentTimeMillis() + timeoutMs;
        while (System.currentTimeMillis() < deadline) {
            if (settlementRepository.existsByPaymentId(paymentId)) return;
            Thread.sleep(200);
        }
        throw new AssertionError("Settlement record not found for paymentId=" + paymentId + " within " + timeoutMs + "ms");
    }

    private List<String> consumeFromKafka(String topic, String expectedKey, long timeoutMs) {
        Map<String, Object> props = Map.of(
                ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, KAFKA.getBootstrapServers(),
                ConsumerConfig.GROUP_ID_CONFIG, "settle-it-" + UUID.randomUUID(),
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
                ConsumerRecords<String, String> records = consumer.poll(Duration.ofMillis(300));
                records.forEach(r -> { if (expectedKey.equals(r.key())) results.add(r.value()); });
                if (!results.isEmpty()) break;
            }
        }
        return results;
    }

    private KafkaProducer<String, String> buildProducer() {
        return new KafkaProducer<>(Map.of(
                ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, KAFKA.getBootstrapServers(),
                ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class,
                ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, StringSerializer.class
        ));
    }

    private String buildRoutedEventJson(String paymentId) {
        return String.format("""
            {
              "paymentId":"%s","correlationId":"%s",
              "amount":2500.00,"currency":"EUR",
              "debtorIban":"DE89370400440532013000",
              "creditorIban":"NL91ABNA0417164300",
              "debtorCountry":"DE","creditorCountry":"NL",
              "railSelected":"SWIFT_MT103",
              "endToEndId":"E2E-%s",
              "enrichedAt":"2026-04-27T10:00:00Z"
            }""", paymentId, UUID.randomUUID(), paymentId.hashCode());
    }
}
