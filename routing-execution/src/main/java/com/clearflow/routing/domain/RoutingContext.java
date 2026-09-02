package com.clearflow.routing.domain;

import java.math.BigDecimal;
import java.util.Map;

public record RoutingContext(
        BigDecimal amount,
        String currency,
        String debtorCountry,
        String creditorCountry,
        String debtorBic,
        String creditorBic,
        String channel,
        boolean valueDateToday,
        Map<String, Object> enrichmentData
) {
    public boolean crossBorder() {
        return !debtorCountry.equalsIgnoreCase(creditorCountry);
    }
}
