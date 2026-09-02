package com.clearflow.gateway.domain;

import io.swagger.v3.oas.annotations.media.Schema;

import java.time.Instant;
import java.util.Map;

@Schema(description = "Payment ingestion response")
public record PaymentResponse(
        String paymentId,
        String correlationId,
        PaymentStatus status,
        Instant timestamp,
        String estimatedSettlementTime,
        String message,
        Map<String, String> _links
) {
}
