package com.clearflow.validation.messaging;

import com.clearflow.common.domain.EnrichedPaymentEvent;
import com.clearflow.common.domain.PaymentInitiatedEvent;
import com.clearflow.common.idempotency.StageIdempotencyGuard;
import com.clearflow.common.messaging.DlqPublisher;
import com.clearflow.common.messaging.KafkaTopics;
import com.clearflow.validation.processor.*;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Metrics;
import org.apache.camel.CamelContext;
import org.apache.camel.Exchange;
import org.apache.camel.support.DefaultExchange;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.stereotype.Component;

import org.slf4j.MDC;

import java.math.BigDecimal;

@Component
public class ValidationKafkaConsumer {

    private static final Logger log = LoggerFactory.getLogger(ValidationKafkaConsumer.class);
    private static final String STAGE = "validation-enrichment";

    private final CamelContext camelContext;
    private final IBANValidationProcessor ibanProcessor;
    private final BICValidationProcessor bicProcessor;
    private final CurrencyValidationProcessor currencyProcessor;
    private final EmbargoPreCheckProcessor embargoProcessor;
    private final EnrichmentProcessor enrichmentProcessor;
    private final KafkaTemplate<String, String> kafkaTemplate;
    private final ObjectMapper objectMapper;
    private final StageIdempotencyGuard idempotencyGuard;
    private final Counter validatedCounter;
    private final Counter rejectedCounter;
    private final Counter fraudBlockedCounter;
    private final DlqPublisher dlqPublisher;
    private final StringRedisTemplate redisTemplate;

    public ValidationKafkaConsumer(CamelContext camelContext,
                                    IBANValidationProcessor ibanProcessor,
                                    BICValidationProcessor bicProcessor,
                                    CurrencyValidationProcessor currencyProcessor,
                                    EmbargoPreCheckProcessor embargoProcessor,
                                    EnrichmentProcessor enrichmentProcessor,
                                    @Qualifier("validationKafkaTemplate") KafkaTemplate<String, String> kafkaTemplate,
                                    ObjectMapper objectMapper,
                                    StageIdempotencyGuard idempotencyGuard,
                                    MeterRegistry meterRegistry,
                                    StringRedisTemplate redisTemplate) {
        this.camelContext      = camelContext;
        this.ibanProcessor     = ibanProcessor;
        this.bicProcessor      = bicProcessor;
        this.currencyProcessor = currencyProcessor;
        this.embargoProcessor  = embargoProcessor;
        this.enrichmentProcessor = enrichmentProcessor;
        this.kafkaTemplate     = kafkaTemplate;
        this.objectMapper      = objectMapper;
        this.idempotencyGuard  = idempotencyGuard;
        this.validatedCounter     = Counter.builder("clearflow_validation_accepted_total").register(meterRegistry);
        this.rejectedCounter      = Counter.builder("clearflow_validation_rejected_total").register(meterRegistry);
        this.fraudBlockedCounter  = Counter.builder("clearflow_validation_fraud_blocked_total")
                .description("Payments blocked at validation stage due to CRITICAL fraud score")
                .register(meterRegistry);
        this.dlqPublisher      = new DlqPublisher(kafkaTemplate, meterRegistry);
        this.redisTemplate     = redisTemplate;
    }

    @KafkaListener(
            topics = KafkaTopics.PAYMENT_INITIATED,
            groupId = "validation-enrichment-kafka",
            containerFactory = "validationKafkaListenerContainerFactory"
    )
    public void onPaymentInitiated(ConsumerRecord<String, String> record, Acknowledgment ack) {
        String paymentId = record.key() != null ? record.key() : "UNKNOWN";
        MDC.put("paymentId", paymentId);
        try {
            if (idempotencyGuard.alreadyProcessed(STAGE, paymentId)) {
                ack.acknowledge();
                return;
            }

            PaymentInitiatedEvent event = objectMapper.readValue(record.value(), PaymentInitiatedEvent.class);
            if (event.correlationId() != null) MDC.put("correlationId", event.correlationId());

            // Build a Camel Exchange so we can reuse existing processor logic unchanged
            Exchange exchange = new DefaultExchange(camelContext);
            exchange.getIn().setBody(event);
            exchange.getIn().setHeader("paymentId",       event.paymentId());
            exchange.getIn().setHeader("correlationId",   event.correlationId());
            exchange.getIn().setHeader("debtorIban",      event.debtorIban());
            exchange.getIn().setHeader("creditorIban",    event.creditorIban());
            exchange.getIn().setHeader("debtorCurrency",  event.currency());
            exchange.getIn().setHeader("creditorCurrency",event.currency());
            exchange.getIn().setHeader("currency",        event.currency());
            exchange.getIn().setHeader("amount",          event.amount());
            exchange.getIn().setHeader("debtorCountry",   event.debtorCountry());
            exchange.getIn().setHeader("creditorCountry", event.creditorCountry());
            exchange.getIn().setHeader("channel",         event.channel());
            exchange.getIn().setHeader("debtorName",      event.debtorName());
            exchange.getIn().setHeader("creditorName",    event.creditorName());
            exchange.getIn().setHeader("debtorBic",       event.debtorBic());
            exchange.getIn().setHeader("creditorBic",     event.creditorBic());

            ibanProcessor.process(exchange);
            bicProcessor.process(exchange);
            currencyProcessor.process(exchange);
            embargoProcessor.process(exchange);
            enrichmentProcessor.process(exchange);

            String status = exchange.getIn().getHeader("validation.status", "VALID", String.class);

            // Fraud gate: check if fraud-scoring already marked this payment CRITICAL
            if ("VALID".equals(status)) {
                try {
                    String fraudJson = redisTemplate.opsForValue().get("fraud:score:" + paymentId);
                    if (fraudJson != null) {
                        JsonNode fraudNode = objectMapper.readTree(fraudJson);
                        String riskBand = fraudNode.path("riskBand").asText("");
                        if ("CRITICAL".equals(riskBand)) {
                            String blockedJson = String.format(
                                    "{\"paymentId\":\"%s\",\"reason\":\"FRAUD_CRITICAL\",\"fraudScore\":%s}",
                                    paymentId, fraudNode.path("fraudScore").asText("1.0"));
                            kafkaTemplate.send(KafkaTopics.PAYMENT_BLOCKED, paymentId, blockedJson);
                            fraudBlockedCounter.increment();
                            log.warn("PAYMENT_BLOCKED_AT_VALIDATION paymentId={} — CRITICAL fraud score detected",
                                    paymentId);
                            ack.acknowledge();
                            return;
                        }
                    }
                } catch (Exception ex) {
                    log.debug("Fraud cache check failed for paymentId={} — proceeding with validation: {}", paymentId, ex.getMessage());
                }
            }

            if ("VALID".equals(status)) {
                EnrichedPaymentEvent enriched = exchange.getIn().getBody(EnrichedPaymentEvent.class);
                kafkaTemplate.send(KafkaTopics.PAYMENT_VALIDATED, paymentId,
                        objectMapper.writeValueAsString(enriched));
                validatedCounter.increment();
                log.info("PAYMENT_VALIDATED paymentId={} debtorCountry={} creditorCountry={} amount={} currency={}",
                        paymentId, event.debtorCountry(), event.creditorCountry(), event.amount(), event.currency());
            } else {
                String reason = exchange.getIn().getHeader("rejection.reason", "UNKNOWN", String.class);
                String rejectedJson = String.format(
                        "{\"paymentId\":\"%s\",\"reason\":\"%s\"}", paymentId, reason);
                kafkaTemplate.send(KafkaTopics.PAYMENT_REJECTED, paymentId, rejectedJson);
                rejectedCounter.increment();
                log.info("PAYMENT_REJECTED paymentId={} reason={}", paymentId, reason);
            }

            ack.acknowledge();

        } catch (Exception ex) {
            log.error("Validation failed paymentId={}: {}", paymentId, ex.getMessage(), ex);
            dlqPublisher.publish(KafkaTopics.PAYMENT_INITIATED, paymentId, record.value(), 1, ex);
            ack.acknowledge();
        } finally {
            MDC.remove("paymentId");
            MDC.remove("correlationId");
        }
    }
}
