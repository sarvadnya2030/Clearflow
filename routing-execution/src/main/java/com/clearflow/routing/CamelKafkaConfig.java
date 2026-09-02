package com.clearflow.routing;

import org.apache.camel.component.kafka.KafkaComponent;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CamelKafkaConfig {

    @Value("${spring.kafka.bootstrap-servers:localhost:9092}")
    private String bootstrapServers;

    @Bean
    public KafkaComponent kafka() {
        KafkaComponent component = new KafkaComponent();
        component.getConfiguration().setBrokers(bootstrapServers);
        return component;
    }
}
