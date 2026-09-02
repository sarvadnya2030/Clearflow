package com.clearflow.settlement.camel;

import org.apache.camel.builder.RouteBuilder;
import org.springframework.stereotype.Component;

// Disabled: settlement now consumes from Kafka via SettlementKafkaConsumer (32 workers).
// Camel dependency kept for SagaCompensationRoute in routing-execution; this route is a no-op.
@Component
public class SettlementCamelRoute extends RouteBuilder {

    @Override
    public void configure() {
        // intentionally empty
    }
}
