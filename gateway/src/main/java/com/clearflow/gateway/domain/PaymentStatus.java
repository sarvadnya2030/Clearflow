package com.clearflow.gateway.domain;

public enum PaymentStatus {
    ACCEPTED,
    INITIATED,
    VALIDATED,
    AML_SCREENED,
    ROUTED,
    LIQUIDITY_RESERVED,
    SETTLED,
    REJECTED,
    BLOCKED,
    FAILED,
    DUPLICATE
}
