package com.clearflow.gateway.domain;

public record IdempotencyResult(boolean duplicate, PaymentResponse cachedResponse) {

    public static IdempotencyResult accepted() {
        return new IdempotencyResult(false, null);
    }

    public static IdempotencyResult duplicate(PaymentResponse response) {
        return new IdempotencyResult(true, response);
    }
}
