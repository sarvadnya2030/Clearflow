package com.clearflow.routing.messaging;

import com.clearflow.common.domain.EnrichedPaymentEvent;
import com.clearflow.common.idempotency.StageIdempotencyGuard;
import com.clearflow.common.messaging.DlqPublisher;
import com.clearflow.common.messaging.KafkaTopics;
import com.fasterxml.jackson.core.type.TypeReference;
import com.clearflow.routing.processor.LiquidityReservationProcessor;
import com.clearflow.routing.processor.RailSelectionProcessor;
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
public class RoutingKafkaConsumer {

    private static final Logger log = LoggerFactory.getLogger(RoutingKafkaConsumer.class);
    private static final String STAGE = "routing-execution";

    private final CamelContext camelContext;
    private final RailSelectionProcessor railProcessor;
    private final LiquidityReservationProcessor liquidityProcessor;
    private final KafkaTemplate<String, String> kafkaTemplate;
    private final ObjectMapper objectMapper;
    private final StageIdempotencyGuard idempotencyGuard;
    private final Counter routedCounter;
    private final Counter failedCounter;
    private final DlqPublisher dlqPublisher;

    public RoutingKafkaConsumer(CamelContext camelContext,
                                 RailSelectionProcessor railProcessor,
                                 LiquidityReservationProcessor liquidityProcessor,
                                 @Qualifier("routingKafkaTemplate") KafkaTemplate<String, String> kafkaTemplate,
                                 ObjectMapper objectMapper,
                                 StageIdempotencyGuard idempotencyGuard,
                                 MeterRegistry meterRegistry) {
        this.camelContext      = camelContext;
        this.railProcessor     = railProcessor;
        this.liquidityProcessor = liquidityProcessor;
        this.kafkaTemplate     = kafkaTemplate;
        this.objectMapper      = objectMapper;
        this.idempotencyGuard  = idempotencyGuard;
        this.routedCounter     = Counter.builder("clearflow_routing_routed_total").register(meterRegistry);
        this.failedCounter     = Counter.builder("clearflow_routing_failed_total").register(meterRegistry);
        this.dlqPublisher      = new DlqPublisher(kafkaTemplate, meterRegistry);
    }

    @KafkaListener(
            topics = KafkaTopics.AML_SANCTIONS_CLEAR,
            groupId = "routing-execution-kafka",
            containerFactory = "routingKafkaListenerContainerFactory"
    )
    public void onSanctionsClear(ConsumerRecord<String, String> record, Acknowledgment ack) {
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
            exchange.getIn().setHeader("paymentId",       event.paymentId());
            exchange.getIn().setHeader("correlationId",   event.correlationId());
            exchange.getIn().setHeader("amount",          event.amount());
            exchange.getIn().setHeader("currency",        event.debtorCurrency());
            exchange.getIn().setHeader("debtorCountry",   event.debtorCountry());
            exchange.getIn().setHeader("creditorCountry", event.creditorCountry());
            exchange.getIn().setHeader("debtorBic",       event.debtorBic());
            exchange.getIn().setHeader("creditorBic",     event.creditorBic());
            exchange.getIn().setHeader("channel",         event.preferredRail());

            railProcessor.process(exchange);
            liquidityProcessor.process(exchange);

            Boolean liquidityOk = exchange.getIn().getHeader("liquidity.reserved", Boolean.FALSE, Boolean.class);
            String payload = objectMapper.writeValueAsString(event);

            if (Boolean.TRUE.equals(liquidityOk)) {
                String rail = exchange.getIn().getHeader("rail.selected", String.class);
                String reservationId = exchange.getIn().getHeader("reservation.id", String.class);
                String nostroAccountId = exchange.getIn().getHeader("nostro.accountId", String.class);
                // Augment payload with routing decision so settlement uses the correct rail
                java.util.Map<String, Object> routedMap = objectMapper.readValue(
                        payload, new TypeReference<java.util.Map<String, Object>>() {});
                routedMap.put("selectedRail", rail);
                routedMap.put("reservationId", reservationId);
                routedMap.put("nostroAccountId", nostroAccountId);
                String routedPayload = objectMapper.writeValueAsString(routedMap);
                kafkaTemplate.send(KafkaTopics.PAYMENT_ROUTED, paymentId, routedPayload);
                routedCounter.increment();
                log.info("PAYMENT_ROUTED paymentId={} rail={} currency={} amount={}",
                        paymentId, rail, event.debtorCurrency(), event.amount());
            } else {
                String error = exchange.getIn().getHeader("liquidity.error", "INSUFFICIENT_LIQUIDITY", String.class);
                String failedJson = String.format(
                        "{\"paymentId\":\"%s\",\"reason\":\"%s\"}", paymentId, error);
                kafkaTemplate.send(KafkaTopics.PAYMENT_FAILED, paymentId, failedJson);
                failedCounter.increment();
                log.warn("ROUTING_FAILED paymentId={} reason={}", paymentId, error);
            }

            ack.acknowledge();

        } catch (Exception ex) {
            log.error("Routing failed paymentId={}: {}", paymentId, ex.getMessage(), ex);
            dlqPublisher.publish(KafkaTopics.AML_SANCTIONS_CLEAR, paymentId, record.value(), 1, ex);
            ack.acknowledge();
        } finally {
            MDC.remove("paymentId");
            MDC.remove("correlationId");
        }
    }
}
