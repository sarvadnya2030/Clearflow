package com.clearflow.compliance.camel;

import org.apache.camel.builder.RouteBuilder;
import org.springframework.stereotype.Component;

// Disabled: AML now consumes from Kafka via AMLKafkaConsumer (16 workers).
@Component
public class AMLCamelRoute extends RouteBuilder {

    @Override
    public void configure() {
        // intentionally empty — replaced by AMLKafkaConsumer
    }
}
