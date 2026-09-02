package com.clearflow.common.idempotency;

import com.clearflow.common.IntegrationTestBase;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = StageIdempotencyGuardIT.TestApp.class)
class StageIdempotencyGuardIT extends IntegrationTestBase {

    @SpringBootApplication(scanBasePackages = "com.clearflow.common.idempotency")
    static class TestApp {}

    @Autowired
    private StageIdempotencyGuard guard;

    @Autowired
    private StringRedisTemplate redis;

    @BeforeEach
    void cleanRedis() {
        redis.getConnectionFactory().getConnection().flushDb();
    }

    @Test
    void firstCallReturnsFalse() {
        assertThat(guard.alreadyProcessed("fraud-scoring", "PAY-001")).isFalse();
    }

    @Test
    void secondCallReturnsTrue() {
        guard.alreadyProcessed("fraud-scoring", "PAY-002");
        assertThat(guard.alreadyProcessed("fraud-scoring", "PAY-002")).isTrue();
    }

    @Test
    void differentStagesSamePaymentAreIndependent() {
        guard.alreadyProcessed("fraud-scoring",  "PAY-003");
        guard.alreadyProcessed("aml-compliance", "PAY-003");

        assertThat(guard.alreadyProcessed("fraud-scoring",  "PAY-003")).isTrue();
        assertThat(guard.alreadyProcessed("aml-compliance", "PAY-003")).isTrue();
        assertThat(guard.alreadyProcessed("settlement",     "PAY-003")).isFalse();
    }

    @Test
    void differentPaymentsSameStageAreIndependent() {
        guard.alreadyProcessed("fraud-scoring", "PAY-004");

        assertThat(guard.alreadyProcessed("fraud-scoring", "PAY-004")).isTrue();
        assertThat(guard.alreadyProcessed("fraud-scoring", "PAY-005")).isFalse();
    }
}
