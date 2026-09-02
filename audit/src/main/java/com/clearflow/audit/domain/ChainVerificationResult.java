package com.clearflow.audit.domain;

import java.time.Instant;

public record ChainVerificationResult(
        boolean valid,
        String paymentId,
        int totalEvents,
        String genesisHash,
        String latestHash,
        Integer tamperDetectedAtBlock,
        Instant verifiedAt
) {
    public static ChainVerificationResult empty(String paymentId) {
        return new ChainVerificationResult(true, paymentId, 0, null, null, null, Instant.now());
    }
}
