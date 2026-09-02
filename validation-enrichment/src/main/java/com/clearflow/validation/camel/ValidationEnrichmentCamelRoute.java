package com.clearflow.validation.camel;

import org.apache.camel.builder.RouteBuilder;
import org.springframework.stereotype.Component;

// Disabled: validation now consumes from Kafka via ValidationKafkaConsumer (16 workers).
@Component
public class ValidationEnrichmentCamelRoute extends RouteBuilder {

    @Override
    public void configure() {
        // intentionally empty — replaced by ValidationKafkaConsumer
    }
}
