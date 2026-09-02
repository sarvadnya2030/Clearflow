package com.clearflow.common.messaging;

public final class KafkaTopics {
    public static final String PAYMENT_INITIATED = "clearflow.payment.initiated";
    public static final String FRAUD_EVALUATED = "clearflow.fraud.evaluated";
    public static final String PAYMENT_BLOCKED = "clearflow.payment.blocked";
    public static final String PAYMENT_VALIDATED = "clearflow.payment.validated";
    public static final String PAYMENT_REJECTED = "clearflow.payment.rejected";
    public static final String AML_SANCTIONS_CLEAR = "clearflow.aml.sanctions.clear";
    public static final String AML_SANCTIONS_HIT = "clearflow.aml.sanctions.hit";
    public static final String COMPLIANCE_ALERTS = "clearflow.compliance.alerts";
    public static final String PAYMENT_ROUTED = "clearflow.payment.routed";
    public static final String PAYMENT_FAILED = "clearflow.payment.failed";
    public static final String PAYMENT_SETTLED = "clearflow.payment.settled";
    public static final String ANALYTICS_SETTLEMENT = "clearflow.analytics.settlement";
    public static final String MCP_ACCESS_LOG = "clearflow.mcp.access.log";
    public static final String PAYMENT_DLQ = "clearflow.payment.dlq";
    public static final String FRAUD_DLQ = "clearflow.fraud.dlq";
    public static final String PAYMENT_SETTLEMENT_FAILED = "clearflow.payment.settlement.failed";
    public static final String PAYMENT_COMPENSATED = "clearflow.payment.compensated";

    private KafkaTopics() {
    }
}
