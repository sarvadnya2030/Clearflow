package com.clearflow.gateway.messaging;

import com.clearflow.common.domain.PaymentInitiatedEvent;
import com.clearflow.common.messaging.SolaceTopics;
import com.clearflow.common.resilience.CircuitBreakerNames;
import io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class SolacePublisher {

    private static final Logger log = LoggerFactory.getLogger(SolacePublisher.class);

    @CircuitBreaker(name = CircuitBreakerNames.SOLACE, fallbackMethod = "publishFallback")
    public void publish(PaymentInitiatedEvent event) {
        String topic = SolaceTopics.PAYMENT_INITIATED_PREFIX + "/" + event.currency() + "/" + event.debtorCountry();
        log.info("solacePublish topic={} paymentId={} correlationId={}", topic, event.paymentId(), event.correlationId());
    }

    @SuppressWarnings("unused")
    void publishFallback(PaymentInitiatedEvent event, Exception ex) {
        log.warn("Solace publish fallback paymentId={} reason={}", event.paymentId(), ex.getMessage());
    }
}
