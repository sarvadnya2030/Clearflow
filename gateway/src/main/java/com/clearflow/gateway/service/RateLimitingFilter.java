package com.clearflow.gateway.service;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

@Service
public class RateLimitingFilter {

    private static final Map<String, Long> TIER_CAPACITY = Map.of(
            "free",   10L,
            "bronze", 100L,
            "silver", 1_000L,
            "gold",   10_000L
    );
    private static final long DEFAULT_CAPACITY = 5_000L;

    private final Map<String, State> states = new ConcurrentHashMap<>();

    public Mono<RateLimitDecision> checkLimit(String clientId) {
        return checkLimit(clientId, null);
    }

    public Mono<RateLimitDecision> checkLimit(String clientId, String tier) {
        long capacity = tier != null
                ? TIER_CAPACITY.getOrDefault(tier.toLowerCase(), DEFAULT_CAPACITY)
                : DEFAULT_CAPACITY;
        // Key includes tier so different tier configs get independent buckets
        String stateKey = clientId + ":" + (tier != null ? tier.toLowerCase() : "default");
        State state = states.computeIfAbsent(stateKey, k -> new State(capacity, System.nanoTime()));
        synchronized (state) {
            long now = System.nanoTime();
            long elapsedNanos = now - state.lastRefillNanos;
            long refill = (elapsedNanos * capacity) / 1_000_000_000L;
            if (refill > 0) {
                state.tokens = Math.min(capacity, state.tokens + refill);
                state.lastRefillNanos = now;
            }
            boolean allowed = state.tokens > 0;
            if (allowed) state.tokens--;
            return Mono.just(new RateLimitDecision(allowed, state.tokens));
        }
    }

    public record RateLimitDecision(boolean allowed, long remaining) {}

    private static final class State {
        long tokens;
        long lastRefillNanos;

        State(long tokens, long lastRefillNanos) {
            this.tokens = tokens;
            this.lastRefillNanos = lastRefillNanos;
        }
    }
}
