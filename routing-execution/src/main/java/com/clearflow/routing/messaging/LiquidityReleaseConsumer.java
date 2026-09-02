package com.clearflow.routing.messaging;

import com.clearflow.common.messaging.KafkaTopics;
import com.clearflow.routing.service.LiquidityReservationService;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.stereotype.Component;

@Component
public class LiquidityReleaseConsumer {

    private static final Logger log = LoggerFactory.getLogger(LiquidityReleaseConsumer.class);

    private final LiquidityReservationService liquidityReservationService;
    private final ObjectMapper objectMapper;

    public LiquidityReleaseConsumer(LiquidityReservationService liquidityReservationService,
                                     ObjectMapper objectMapper) {
        this.liquidityReservationService = liquidityReservationService;
        this.objectMapper = objectMapper;
    }

    @KafkaListener(
            topics = KafkaTopics.PAYMENT_SETTLED,
            groupId = "routing-liquidity-release",
            containerFactory = "routingKafkaListenerContainerFactory"
    )
    public void onPaymentSettled(ConsumerRecord<String, String> record, Acknowledgment ack) {
        String paymentId = record.key() != null ? record.key() : extractPaymentId(record.value());
        try {
            liquidityReservationService.release(paymentId);
            log.debug("LIQUIDITY_RELEASED paymentId={}", paymentId);
        } catch (Exception ex) {
            log.warn("Liquidity release skipped paymentId={}: {}", paymentId, ex.getMessage());
        } finally {
            ack.acknowledge();
        }
    }

    private String extractPaymentId(String json) {
        try {
            JsonNode node = objectMapper.readTree(json);
            return node.path("paymentId").asText("UNKNOWN");
        } catch (Exception e) {
            return "UNKNOWN";
        }
    }
}
