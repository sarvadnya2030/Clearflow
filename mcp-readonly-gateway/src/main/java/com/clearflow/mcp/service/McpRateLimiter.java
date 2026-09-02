package com.clearflow.mcp.service;

import org.springframework.stereotype.Component;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

@Component
public class McpRateLimiter {

    private static final long CAPACITY = 20;
    private static final long REFILL_PER_MINUTE = 20;
    private final Map<String, State> buckets = new ConcurrentHashMap<>();

    public boolean allow(String subject) {
        State state = buckets.computeIfAbsent(subject, s -> new State(CAPACITY, System.nanoTime()));
        synchronized (state) {
            long now = System.nanoTime();
            long elapsedNanos = now - state.lastRefillNanos;
            long refill = (elapsedNanos * REFILL_PER_MINUTE) / 60_000_000_000L;
            if (refill > 0) {
                state.tokens = Math.min(CAPACITY, state.tokens + refill);
                state.lastRefillNanos = now;
            }
            if (state.tokens <= 0) {
                return false;
            }
            state.tokens--;
            return true;
        }
    }

    private static final class State {
        long tokens;
        long lastRefillNanos;

        State(long tokens, long lastRefillNanos) {
            this.tokens = tokens;
            this.lastRefillNanos = lastRefillNanos;
        }
    }
}
