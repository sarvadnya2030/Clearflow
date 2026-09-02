package com.clearflow.gateway.domain;

import java.time.Instant;

public record PaymentStatusResponse(
        String paymentId,
        PaymentStatus status,
        String stage,
        String message,
        Instant updatedAt
) {
    public PaymentStatusResponse(String paymentId, PaymentStatus status,
                                 String message, Instant updatedAt) {
        this(paymentId, status, "gateway", message, updatedAt);
    }
}
