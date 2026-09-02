package com.clearflow.fraud.domain;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Map;

public record FraudResponse(
        String paymentId,
        BigDecimal fraudScore,
        RiskBand riskBand,
        Map<String, Double> featureImportance,
        String modelVersion,
        Instant scoredAt,
        long processingTimeMs,
        boolean fallbackUsed
) {
}
