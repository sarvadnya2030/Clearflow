package com.clearflow.fraud.domain;

import java.math.BigDecimal;
import java.time.Instant;

public record FraudRequest(
        String paymentId,
        String correlationId,
        String debtorIban,
        String creditorIban,
        BigDecimal amount,
        String currency,
        String debtorCountry,
        String creditorCountry,
        String channel,
        Instant initiatedAt
) {
}
