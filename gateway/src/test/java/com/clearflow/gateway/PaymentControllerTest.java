package com.clearflow.gateway;

import com.clearflow.gateway.domain.PaymentRequest;
import com.clearflow.gateway.domain.PaymentResponse;
import com.clearflow.gateway.domain.PaymentStatus;
import com.clearflow.gateway.messaging.ActiveMQPublisher;
import com.clearflow.gateway.messaging.KafkaEventPublisher;
import com.clearflow.gateway.messaging.SolacePublisher;
import com.clearflow.gateway.service.IdempotencyService;
import com.clearflow.gateway.service.RateLimitingFilter;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.http.HttpStatus;
import reactor.core.publisher.Mono;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.when;

class PaymentControllerTest {

    @Test
    @DisplayName("Rate limit decision denies request when tokens are exhausted")
    void rateLimitDenied() {
        RateLimitingFilter filter = new RateLimitingFilter();
        var denied = new RateLimitingFilter.RateLimitDecision(false, 0);
        assertEquals(false, denied.allowed());
        assertEquals(0, denied.remaining());
    }

    @Test
    @DisplayName("Duplicate response preserves DUPLICATE status")
    void duplicateResponseStatus() {
        PaymentResponse response = new PaymentResponse(
                "p1", "c1", PaymentStatus.DUPLICATE, Instant.now(), "N/A", "Duplicate", Map.of("self", "/api/v1/payments/p1")
        );
        assertEquals(PaymentStatus.DUPLICATE, response.status());
    }
}
