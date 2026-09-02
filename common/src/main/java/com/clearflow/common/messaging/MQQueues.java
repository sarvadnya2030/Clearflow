package com.clearflow.common.messaging;

public final class MQQueues {
    public static final String PAYMENT_INITIATED = "CLEARFLOW.PAYMENT.INITIATED";
    public static final String PAYMENT_VALIDATED = "CLEARFLOW.PAYMENT.VALIDATED";
    public static final String PAYMENT_REJECTED = "CLEARFLOW.PAYMENT.REJECTED";
    public static final String PAYMENT_SANCTIONS_HIT = "CLEARFLOW.PAYMENT.SANCTIONS.HIT";
    public static final String PAYMENT_SANCTIONS_CLEAR = "CLEARFLOW.PAYMENT.SANCTIONS.CLEAR";
    public static final String PAYMENT_ROUTED = "CLEARFLOW.PAYMENT.ROUTED";
    public static final String PAYMENT_SETTLED = "CLEARFLOW.PAYMENT.SETTLED";
    public static final String PAYMENT_DLQ = "CLEARFLOW.PAYMENT.DLQ";
    public static final String PAYMENT_INSUFFICIENT_LIQUIDITY = "CLEARFLOW.PAYMENT.INSUFFICIENT.LIQUIDITY";
    public static final String PAYMENT_SETTLEMENT_FAILED = "CLEARFLOW.PAYMENT.SETTLEMENT.FAILED";
    public static final String PAYMENT_COMPENSATED = "CLEARFLOW.PAYMENT.COMPENSATED";

    private MQQueues() {
    }
}
