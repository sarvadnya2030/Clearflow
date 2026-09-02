package com.clearflow.gateway.messaging;

import com.clearflow.common.domain.PaymentInitiatedEvent;
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * Outbox entry stored in Redis LIST `outbox:pending`.
 * Carries everything the relay needs to reconstruct and send the Kafka message.
 */
public record PaymentOutboxEntry(
        String paymentId,
        String traceParent,
        String traceState,
        PaymentInitiatedEvent event,
        int attempts
) {
    @JsonCreator
    public PaymentOutboxEntry(
            @JsonProperty("paymentId")  String paymentId,
            @JsonProperty("traceParent") String traceParent,
            @JsonProperty("traceState")  String traceState,
            @JsonProperty("event")       PaymentInitiatedEvent event,
            @JsonProperty("attempts")    int attempts) {
        this.paymentId  = paymentId;
        this.traceParent = traceParent;
        this.traceState  = traceState;
        this.event       = event;
        this.attempts    = attempts;
    }

    public PaymentOutboxEntry withAttempt() {
        return new PaymentOutboxEntry(paymentId, traceParent, traceState, event, attempts + 1);
    }
}
