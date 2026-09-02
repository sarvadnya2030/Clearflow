package com.clearflow.gateway.status;

import com.clearflow.gateway.domain.PaymentStatus;
import com.clearflow.gateway.domain.PaymentStatusResponse;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.core.ReactiveRedisTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

import java.time.Duration;
import java.time.Instant;

@Service
public class PaymentStatusService {

    private static final Logger log = LoggerFactory.getLogger(PaymentStatusService.class);
    private static final String KEY_PREFIX = "payment:status:";
    private static final Duration TTL = Duration.ofHours(2);

    private final ReactiveRedisTemplate<String, String> redisTemplate;
    private final ObjectMapper objectMapper;

    public PaymentStatusService(ReactiveRedisTemplate<String, String> redisTemplate,
                                ObjectMapper objectMapper) {
        this.redisTemplate = redisTemplate;
        this.objectMapper = objectMapper;
    }

    public Mono<Void> updateStatus(String paymentId, PaymentStatus status, String stage, String detail) {
        PaymentStatusResponse response = new PaymentStatusResponse(paymentId, status, stage, detail, Instant.now());
        String json;
        try {
            json = objectMapper.writeValueAsString(response);
        } catch (JsonProcessingException e) {
            log.error("Failed to serialize PaymentStatusResponse for paymentId={}", paymentId, e);
            return Mono.empty();
        }
        return redisTemplate.opsForValue()
                .set(KEY_PREFIX + paymentId, json, TTL)
                .then();
    }

    public Mono<Void> storeUetrMapping(String uetr, String paymentId) {
        return redisTemplate.opsForValue()
                .set("payment:uetr:" + uetr, paymentId, TTL)
                .then();
    }

    public Mono<String> getPaymentIdByUetr(String uetr) {
        return redisTemplate.opsForValue().get("payment:uetr:" + uetr);
    }

    public Mono<PaymentStatusResponse> getStatus(String paymentId) {
        return redisTemplate.opsForValue()
                .get(KEY_PREFIX + paymentId)
                .flatMap(json -> {
                    try {
                        return Mono.just(objectMapper.readValue(json, PaymentStatusResponse.class));
                    } catch (JsonProcessingException e) {
                        log.error("Failed to deserialize PaymentStatusResponse for paymentId={}", paymentId, e);
                        return Mono.empty();
                    }
                })
                .switchIfEmpty(Mono.just(new PaymentStatusResponse(
                        paymentId, PaymentStatus.ACCEPTED,
                        "gateway", "Status tracking sourced from orchestration timeline", Instant.now())));
    }
}
