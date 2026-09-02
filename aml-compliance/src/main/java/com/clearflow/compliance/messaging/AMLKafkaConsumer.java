package com.clearflow.compliance.messaging;

import com.clearflow.common.domain.EnrichedPaymentEvent;
import com.clearflow.common.idempotency.StageIdempotencyGuard;
import com.clearflow.common.messaging.DlqPublisher;
import com.clearflow.common.messaging.KafkaTopics;
import com.clearflow.compliance.processor.AMLScreeningProcessor;
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
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.Acknowledgment;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;

@Component
public class AMLKafkaConsumer {

    private static final Logger log = LoggerFactory.getLogger(AMLKafkaConsumer.class);
    private static final String STAGE = "aml-compliance";

    private final CamelContext camelContext;
    private final AMLScreeningProcessor amlProcessor;
    private final KafkaTemplate<String, String> kafkaTemplate;
    private final ObjectMapper objectMapper;
    private final StageIdempotencyGuard idempotencyGuard;
    private final Counter clearCounter;
    private final Counter hitCounter;
    private final DlqPublisher dlqPublisher;

    public AMLKafkaConsumer(CamelContext camelContext,
                             AMLScreeningProcessor amlProcessor,
                             @Qualifier("amlKafkaTemplate") KafkaTemplate<String, String> kafkaTemplate,
                             ObjectMapper objectMapper,
                             StageIdempotencyGuard idempotencyGuard,
                             MeterRegistry meterRegistry) {
        this.camelContext     = camelContext;
        this.amlProcessor     = amlProcessor;
        this.kafkaTemplate    = kafkaTemplate;
        this.objectMapper     = objectMapper;
        this.idempotencyGuard = idempotencyGuard;
        this.clearCounter     = Counter.builder("clearflow_aml_clear_total").register(meterRegistry);
        this.hitCounter       = Counter.builder("clearflow_aml_hit_total").register(meterRegistry);
        this.dlqPublisher     = new DlqPublisher(kafkaTemplate, meterRegistry);
    }

    @KafkaListener(
            topics = KafkaTopics.PAYMENT_VALIDATED,
            groupId = "aml-compliance-kafka",
            containerFactory = "amlKafkaListenerContainerFactory"
    )
    public void onPaymentValidated(ConsumerRecord<String, String> record, Acknowledgment ack) {
        String paymentId = record.key() != null ? record.key() : "UNKNOWN";
        MDC.put("paymentId", paymentId);
        try {
            if (idempotencyGuard.alreadyProcessed(STAGE, paymentId)) {
                ack.acknowledge();
                return;
            }

            EnrichedPaymentEvent event = objectMapper.readValue(record.value(), EnrichedPaymentEvent.class);
            if (event.correlationId() != null) MDC.put("correlationId", event.correlationId());

            Exchange exchange = new DefaultExchange(camelContext);
            exchange.getIn().setBody(event);
            exchange.getIn().setHeader("paymentId",     event.paymentId());
            exchange.getIn().setHeader("correlationId", event.correlationId());
            exchange.getIn().setHeader("debtorName",    event.debtorName() != null ? event.debtorName() : "");
            exchange.getIn().setHeader("creditorName",  event.creditorName() != null ? event.creditorName() : "");
            exchange.getIn().setHeader("debtorIban",    event.debtorIban());
            exchange.getIn().setHeader("creditorIban",  event.creditorIban());
            exchange.getIn().setHeader("amount",        event.amount());
            exchange.getIn().setHeader("currency",      event.debtorCurrency());

            amlProcessor.process(exchange);

            String amlState = exchange.getIn().getHeader("aml.state", "CLEAR", String.class);
            String payload = objectMapper.writeValueAsString(event);

            // Gate: only CLEAR proceeds to routing. HOLD/ESCALATED stop here --
            // the payment does NOT reach AML_SANCTIONS_CLEAR until a compliance
            // reviewer explicitly resolves it (see ComplianceReviewController),
            // which replays the stored payload forward. Previously this gate
            // didn't exist: a HIT only produced a log line and a status label,
            // nothing stopped the payment or gated a resubmission.
            if ("HOLD".equals(amlState) || "ESCALATED".equals(amlState)) {
                kafkaTemplate.send(KafkaTopics.AML_SANCTIONS_HIT, paymentId, payload);
                kafkaTemplate.send(KafkaTopics.COMPLIANCE_ALERTS, paymentId, payload);
                hitCounter.increment();
                log.warn("AML_HOLD paymentId={} amlState={}", paymentId, amlState);
            } else {
                kafkaTemplate.send(KafkaTopics.AML_SANCTIONS_CLEAR, paymentId, payload);
                clearCounter.increment();
                log.info("AML_SCREENING_COMPLETE paymentId={} amlState=CLEAR", paymentId);
            }

            ack.acknowledge();

        } catch (Exception ex) {
            log.error("AML screening failed paymentId={}: {}", paymentId, ex.getMessage(), ex);
            dlqPublisher.publish(KafkaTopics.PAYMENT_VALIDATED, paymentId, record.value(), 1, ex);
            ack.acknowledge();
        } finally {
            MDC.remove("paymentId");
            MDC.remove("correlationId");
        }
    }
}
