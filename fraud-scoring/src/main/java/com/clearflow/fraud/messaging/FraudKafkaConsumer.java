package com.clearflow.fraud.messaging;

import com.clearflow.common.domain.FraudEvaluatedEvent;
import com.clearflow.common.domain.PaymentInitiatedEvent;
import com.clearflow.common.idempotency.StageIdempotencyGuard;
import com.clearflow.common.messaging.DlqPublisher;
import com.clearflow.common.messaging.KafkaTopics;
import com.clearflow.fraud.domain.FraudRequest;
import com.clearflow.fraud.domain.FraudResponse;
import com.clearflow.fraud.domain.RiskBand;
import com.clearflow.fraud.service.FraudScoringService;
import com.clearflow.fraud.service.VelocityCheckService;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.Acknowledgment;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;

import java.time.Duration;

@Component
public class FraudKafkaConsumer {

    private static final Logger log = LoggerFactory.getLogger(FraudKafkaConsumer.class);
    private static final String STAGE = "fraud-scoring";

    private final FraudScoringService fraudScoringService;
    private final VelocityCheckService velocityCheckService;
    private final StringRedisTemplate redisTemplate;
    private final KafkaTemplate<String, String> kafkaTemplate;
    private final ObjectMapper objectMapper;
    private final StageIdempotencyGuard idempotencyGuard;
    private final DlqPublisher dlqPublisher;
    private final Counter scoredCounter;

    public FraudKafkaConsumer(FraudScoringService fraudScoringService,
                              VelocityCheckService velocityCheckService,
                              StringRedisTemplate redisTemplate,
                              @Qualifier("fraudStringKafkaTemplate") KafkaTemplate<String, String> kafkaTemplate,
                              ObjectMapper objectMapper,
                              StageIdempotencyGuard idempotencyGuard,
                              MeterRegistry meterRegistry) {
        this.fraudScoringService = fraudScoringService;
        this.velocityCheckService = velocityCheckService;
        this.redisTemplate = redisTemplate;
        this.kafkaTemplate = kafkaTemplate;
        this.objectMapper = objectMapper;
        this.idempotencyGuard = idempotencyGuard;
        this.dlqPublisher = new DlqPublisher(kafkaTemplate, meterRegistry);
        this.scoredCounter = Counter.builder("clearflow_fraud_scored_total")
                .description("Payments scored by fraud engine")
                .register(meterRegistry);
    }

    @KafkaListener(
            topics = KafkaTopics.PAYMENT_INITIATED,
            groupId = "fraud-scoring",
            containerFactory = "kafkaListenerContainerFactory"
    )
    public void onPaymentInitiated(ConsumerRecord<String, String> record, Acknowledgment ack) {
        String paymentId = record.key() != null ? record.key() : "UNKNOWN";
        MDC.put("paymentId", paymentId);
        try {
            if (idempotencyGuard.alreadyProcessed(STAGE, paymentId)) {
                log.debug("Duplicate fraud event skipped paymentId={}", paymentId);
                ack.acknowledge();
                return;
            }

            PaymentInitiatedEvent event = objectMapper.readValue(record.value(), PaymentInitiatedEvent.class);
            if (event.correlationId() != null) MDC.put("correlationId", event.correlationId());
            FraudRequest request = new FraudRequest(
                    event.paymentId(), event.correlationId(),
                    event.debtorIban(), event.creditorIban(),
                    event.amount(), event.currency(),
                    event.debtorCountry(), event.creditorCountry(),
                    event.channel(), event.initiatedAt()
            );

            velocityCheckService.addPayment(event.debtorIban(), event.paymentId(), System.currentTimeMillis());
            FraudResponse response = fraudScoringService.score(request);

            try {
                redisTemplate.opsForValue().set(
                        "fraud:score:" + event.paymentId(),
                        objectMapper.writeValueAsString(response),
                        Duration.ofMinutes(10));
            } catch (JsonProcessingException e) {
                log.warn("Unable to cache fraud response paymentId={}", event.paymentId(), e);
            }

            FraudEvaluatedEvent evaluatedEvent = new FraudEvaluatedEvent(
                    response.paymentId(), event.correlationId(),
                    response.fraudScore(), response.riskBand().name(),
                    response.featureImportance(), response.modelVersion(),
                    response.fallbackUsed(), response.scoredAt(), response.processingTimeMs()
            );

            String evaluatedJson = objectMapper.writeValueAsString(evaluatedEvent);
            kafkaTemplate.send(KafkaTopics.FRAUD_EVALUATED, event.paymentId(), evaluatedJson);
            if (response.riskBand() == RiskBand.CRITICAL) {
                kafkaTemplate.send(KafkaTopics.PAYMENT_BLOCKED, event.paymentId(), evaluatedJson);
            }

            scoredCounter.increment();
            log.info("FRAUD_SCORE_COMPUTED paymentId={} riskBand={} score={}", paymentId, response.riskBand(), response.fraudScore());
            ack.acknowledge();

        } catch (Exception ex) {
            log.error("Fraud scoring failed paymentId={}: {}", paymentId, ex.getMessage(), ex);
            dlqPublisher.publish(KafkaTopics.PAYMENT_INITIATED, paymentId,
                    record.value(), 1, ex);
            ack.acknowledge();
        } finally {
            MDC.remove("paymentId");
            MDC.remove("correlationId");
        }
    }
}
