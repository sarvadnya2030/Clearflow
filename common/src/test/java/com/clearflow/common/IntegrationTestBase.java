package com.clearflow.common;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.KafkaContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

/**
 * Base class for integration tests requiring Kafka and Redis.
 *
 * Containers are started once per test suite (static) and shared across all
 * subclasses — startup cost ~4 seconds, not paid per test method.
 *
 * Usage:
 * <pre>
 *   &#64;SpringBootTest
 *   class MyIT extends IntegrationTestBase { ... }
 * </pre>
 */
@Testcontainers
public abstract class IntegrationTestBase {

    @Container
    protected static final KafkaContainer KAFKA = new KafkaContainer(
            DockerImageName.parse("confluentinc/cp-kafka:7.6.1"))
            .withReuse(true);

    @Container
    @SuppressWarnings("resource")
    protected static final GenericContainer<?> REDIS = new GenericContainer<>(
            DockerImageName.parse("redis:7.2-alpine"))
            .withExposedPorts(6379)
            .withCommand("redis-server", "--requirepass", "testpass")
            .withReuse(true);

    @DynamicPropertySource
    static void overrideProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.kafka.bootstrap-servers", KAFKA::getBootstrapServers);
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add("spring.data.redis.port", () -> REDIS.getMappedPort(6379));
        registry.add("spring.data.redis.password", () -> "testpass");
        // Disable Vault and Config Server in tests
        registry.add("spring.cloud.vault.enabled", () -> "false");
        registry.add("spring.cloud.config.enabled", () -> "false");
        registry.add("spring.config.import", () -> "");
    }
}
