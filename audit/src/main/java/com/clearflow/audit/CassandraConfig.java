package com.clearflow.audit;

import com.datastax.oss.driver.api.core.CqlSessionBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.cassandra.CqlSessionBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CassandraConfig {

    @Value("${spring.data.cassandra.keyspace-name:clearflow}")
    private String keyspaceName;

    @Bean
    public CqlSessionBuilderCustomizer localDatacenterCustomizer() {
        return (CqlSessionBuilder builder) -> builder
                .withLocalDatacenter("datacenter1")
                .withKeyspace(keyspaceName);
    }
}
