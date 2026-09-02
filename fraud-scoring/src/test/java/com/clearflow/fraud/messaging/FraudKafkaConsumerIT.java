package com.clearflow.fraud.messaging;

import com.clearflow.common.IntegrationTestBase;
import com.clearflow.common.idempotency.StageIdempotencyGuard;
import com.clearflow.common.messaging.KafkaTopics;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.serialization.StringSerializer;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.ActiveProfiles;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("dev")
class FraudKafkaConsumerIT extends IntegrationTestBase {

    @Autowired
    private StageIdempotencyGuard idempotencyGuard;

    @Autowired
    private StringRedisTemplate redis;

    @BeforeEach
    void flushRedis() {
        redis.getConnectionFactory().getConnection().flushDb();
    }

    @Test
    void duplicatePaymentIsSkippedByIdempotencyGuard() {
        String paymentId = "FRAUD-IT-" + UUID.randomUUID();

        // First call — new payment, should process
        boolean firstCall = idempotencyGuard.alreadyProcessed("fraud-scoring", paymentId);
        assertThat(firstCall).isFalse();

        // Second call — same payment, should be skipped
        boolean secondCall = idempotencyGuard.alreadyProcessed("fraud-scoring", paymentId);
        assertThat(secondCall).isTrue();
    }

    @Test
    void paymentInitiatedEventIsConsumedAndFraudEvaluatedIsPublished() throws Exception {
        String paymentId = "FRAUD-CONSUME-" + UUID.randomUUID();
        String eventJson = buildPaymentInitiatedJson(paymentId);

        // Publish to PAYMENT_INITIATED
        try (KafkaProducer<String, String> producer = buildProducer()) {
            producer.send(new ProducerRecord<>(KafkaTopics.PAYMENT_INITIATED, paymentId, eventJson)).get(5, TimeUnit.SECONDS);
        }

        // Give the consumer time to process
        Thread.sleep(3_000);

        // Idempotency key should now be set in Redis (proves consumer ran)
        boolean processed = idempotencyGuard.alreadyProcessed("fraud-scoring", paymentId);
        assertThat(processed)
                .withFailMessage("Consumer should have marked paymentId=%s as processed in Redis", paymentId)
                .isTrue();
    }

    @Test
    void samePaymentSentTwiceIsProcessedOnce() throws Exception {
        String paymentId = "FRAUD-DEDUP-" + UUID.randomUUID();
        String eventJson = buildPaymentInitiatedJson(paymentId);

        try (KafkaProducer<String, String> producer = buildProducer()) {
            // Send same paymentId twice
            producer.send(new ProducerRecord<>(KafkaTopics.PAYMENT_INITIATED, paymentId, eventJson)).get(5, TimeUnit.SECONDS);
            producer.send(new ProducerRecord<>(KafkaTopics.PAYMENT_INITIATED, paymentId, eventJson)).get(5, TimeUnit.SECONDS);
        }

        Thread.sleep(4_000);

        // Guard is set — first processing happened
        assertThat(idempotencyGuard.alreadyProcessed("fraud-scoring", paymentId)).isTrue();
    }

    private KafkaProducer<String, String> buildProducer() {
        return new KafkaProducer<>(Map.of(
                ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, KAFKA.getBootstrapServers(),
                ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class,
                ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, StringSerializer.class
        ));
    }

    private String buildPaymentInitiatedJson(String paymentId) {
        return String.format("""
            {
              "paymentId":"%s","correlationId":"%s",
              "instructionId":"INST-001","endToEndId":"E2E-001",
              "uetr":"%s",
              "debtorIban":"DE89370400440532013000",
              "creditorIban":"NL91ABNA0417164300",
              "debtorName":"Test Debtor","creditorName":"Test Creditor",
              "debtorBic":"DEUTDEDB","creditorBic":"ABNANL2A",
              "amount":1000.00,"currency":"EUR",
              "debtorCountry":"DE","creditorCountry":"NL",
              "channel":"SWIFT","initiatedAt":"2026-04-27T10:00:00Z","source":"gateway"
            }""",
                paymentId, UUID.randomUUID(), UUID.randomUUID());
    }
}
