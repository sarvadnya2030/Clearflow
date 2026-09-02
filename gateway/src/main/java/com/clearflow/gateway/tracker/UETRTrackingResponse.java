package com.clearflow.gateway.tracker;

import java.time.Instant;
import java.util.List;

public record UETRTrackingResponse(
    String uetr,
    String paymentId,
    String status,           // ACSC / ACCC / RJCT / PDNG
    String statusDescription,
    String rail,
    Instant submittedAt,
    Instant lastUpdatedAt,
    List<TrackerEvent> events
) {
    public record TrackerEvent(
        String stage,
        String agentName,
        String status,       // COMPLETED / FAILED / PENDING
        Instant timestamp,
        String detail
    ) {}
}
