package com.clearflow.common.idempotency;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

import java.time.Duration;

/**
 * Redis-backed per-stage idempotency guard.
 *
 * Before processing a message, call {@link #alreadyProcessed(String, String)}.
 * The key {@code processed:<stage>:<paymentId>} is set with a 24-hour TTL on
 * first processing; subsequent calls return {@code true} so the caller can
 * acknowledge and skip without re-processing.
 *
 * Fails open on Redis errors (returns false) so a Redis outage doesn't block
 * the pipeline — at-least-once semantics remain.
 */
@Component
public class StageIdempotencyGuard {

    private static final Logger log = LoggerFactory.getLogger(StageIdempotencyGuard.class);
    private static final Duration TTL = Duration.ofHours(24);

    private final StringRedisTemplate redis;

    public StageIdempotencyGuard(StringRedisTemplate redis) {
        this.redis = redis;
    }

    /**
     * @return true if this (stage, paymentId) pair has already been processed.
     *         Returns false on Redis error (fail-open).
     */
    public boolean alreadyProcessed(String stage, String paymentId) {
        String key = "processed:" + stage + ":" + paymentId;
        try {
            Boolean wasAbsent = redis.opsForValue().setIfAbsent(key, "1", TTL);
            // wasAbsent=true  → key was absent → we just set it → first time → NOT a duplicate
            // wasAbsent=false → key existed   → already processed → IS a duplicate
            // wasAbsent=null  → Redis error   → fail open → NOT a duplicate
            boolean duplicate = Boolean.FALSE.equals(wasAbsent);
            if (duplicate) {
                log.info("Idempotency skip stage={} paymentId={}", stage, paymentId);
            }
            return duplicate;
        } catch (Exception ex) {
            log.warn("StageIdempotencyGuard Redis error for stage={} paymentId={} — failing open: {}",
                    stage, paymentId, ex.getMessage());
            return false;
        }
    }
}
