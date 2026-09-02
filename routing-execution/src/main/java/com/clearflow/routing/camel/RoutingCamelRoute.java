package com.clearflow.routing.camel;

import org.apache.camel.builder.RouteBuilder;
import org.springframework.stereotype.Component;

// Disabled: routing now consumes from Kafka via RoutingKafkaConsumer (16 workers).
@Component
public class RoutingCamelRoute extends RouteBuilder {

    @Override
    public void configure() {
        // intentionally empty — replaced by RoutingKafkaConsumer
    }
}
