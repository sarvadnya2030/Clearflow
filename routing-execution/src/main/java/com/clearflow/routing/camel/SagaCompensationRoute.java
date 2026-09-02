package com.clearflow.routing.camel;

import com.clearflow.common.messaging.KafkaTopics;
import com.clearflow.common.messaging.MQQueues;
import com.clearflow.routing.service.LiquidityReservationService;
import org.apache.camel.Exchange;
import org.apache.camel.builder.RouteBuilder;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * Saga Compensation Route — releases liquidity reservations when settlement fails.
 *
 * <h3>Choreography-based Saga</h3>
 * <ol>
 *   <li>routing-execution reserves liquidity (nostro debit) via
 *       {@link LiquidityReservationService#reserve}</li>
 *   <li>Payment is forwarded to settlement service</li>
 *   <li>On settlement failure, settlement publishes to
 *       {@value MQQueues#PAYMENT_SETTLEMENT_FAILED}</li>
 *   <li>This route executes the compensating transaction:
 *       {@link LiquidityReservationService#release} — restores nostro balance</li>
 *   <li>A {@code PAYMENT_COMPENSATED} Kafka event is published for audit</li>
 * </ol>
 *
 * <h3>Idempotency</h3>
 * {@code release()} only affects rows with {@code status = 'RESERVED'}.
 * Duplicate delivery of the failure message is a no-op.
 *
 * <h3>DLQ failover</h3>
 * If the compensation itself fails, the exception propagates and Artemis
 * redelivers up to {@code maxDeliveryAttempts} times before routing to
 * {@value MQQueues#PAYMENT_DLQ} for operator review.
 */
@Component
public class SagaCompensationRoute extends RouteBuilder {

    private static final Logger log = LoggerFactory.getLogger(SagaCompensationRoute.class);

    private final LiquidityReservationService liquidityReservationService;

    public SagaCompensationRoute(LiquidityReservationService liquidityReservationService) {
        this.liquidityReservationService = liquidityReservationService;
    }

    @Override
    public void configure() {
        from("jms:queue:" + MQQueues.PAYMENT_SETTLEMENT_FAILED)
            .routeId("saga-compensation-route")
            .log("Saga compensation triggered: paymentId=${header.paymentId} rail=${header.rail.selected}")
            .process(this::compensate)
            .choice()
                .when(header("compensation.success").isEqualTo(true))
                    .to("kafka:" + KafkaTopics.PAYMENT_COMPENSATED)
                    .log("Liquidity released: paymentId=${header.paymentId}")
                .otherwise()
                    .log("No reservation found (already released or never reserved): paymentId=${header.paymentId}")
            .end();
    }

    private void compensate(Exchange exchange) {
        String paymentId = exchange.getIn().getHeader("paymentId", String.class);
        if (paymentId == null || paymentId.isBlank()) {
            log.warn("SagaCompensationRoute: missing paymentId header");
            exchange.getIn().setHeader("compensation.success", false);
            return;
        }
        try {
            liquidityReservationService.release(paymentId);
            exchange.getIn().setHeader("compensation.success", true);
            exchange.getIn().setHeader("compensation.timestamp", java.time.Instant.now().toString());
        } catch (Exception ex) {
            log.error("Saga compensation failed for paymentId={}: {}", paymentId, ex.getMessage(), ex);
            throw new RuntimeException("Saga compensation failed for paymentId=" + paymentId, ex);
        }
    }
}
