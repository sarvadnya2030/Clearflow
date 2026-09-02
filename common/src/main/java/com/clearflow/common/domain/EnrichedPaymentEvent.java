package com.clearflow.common.domain;

import java.io.Serializable;
import java.math.BigDecimal;
import java.time.Instant;

public record EnrichedPaymentEvent(
        String paymentId,
        String correlationId,
        String debtorIban,
        String creditorIban,
        String debtorBic,
        String creditorBic,
        String debtorCountry,
        String creditorCountry,
        BigDecimal amount,
        String debtorCurrency,
        String creditorCurrency,
        String preferredRail,
        int expectedSettlementHours,
        String customerTier,
        String kycStatus,
        Instant enrichedAt,
        String debtorName,
        String creditorName
) implements Serializable {
}
