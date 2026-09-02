package com.clearflow.fraud.service;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.util.Objects;

@Service
public class VelocityCheckService {

    private final StringRedisTemplate redisTemplate;

    public VelocityCheckService(StringRedisTemplate redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    public void addPayment(String debtorIban, String paymentId, long epochMillis) {
        String key = "velocity:" + debtorIban;
        redisTemplate.opsForZSet().add(key, paymentId, epochMillis);
        redisTemplate.expire(key, Duration.ofHours(25));
    }

    public long countLast1h(String debtorIban) {
        long now = System.currentTimeMillis();
        Long count = redisTemplate.opsForZSet().count("velocity:" + debtorIban, now - 3_600_000L, now);
        return Objects.requireNonNullElse(count, 0L);
    }

    public long countLast24h(String debtorIban) {
        long now = System.currentTimeMillis();
        Long count = redisTemplate.opsForZSet().count("velocity:" + debtorIban, now - 86_400_000L, now);
        return Objects.requireNonNullElse(count, 0L);
    }

    public boolean isFirstTimePair(String debtorIban, String creditorIban) {
        String key = "pairs:" + debtorIban;
        Boolean member = redisTemplate.opsForSet().isMember(key, creditorIban);
        if (Boolean.TRUE.equals(member)) {
            return false;
        }
        redisTemplate.opsForSet().add(key, creditorIban);
        redisTemplate.expire(key, Duration.ofHours(25));
        return true;
    }
}
