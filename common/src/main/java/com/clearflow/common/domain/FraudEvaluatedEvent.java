package com.clearflow.common.domain;

import java.io.Serializable;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Map;

public record FraudEvaluatedEvent(
        String paymentId,
        String correlationId,
        BigDecimal fraudScore,
        String riskBand,
        Map<String, Double> featureImportance,
        String modelVersion,
        boolean fallbackUsed,
        Instant scoredAt,
        long processingTimeMs
) implements Serializable {
}
