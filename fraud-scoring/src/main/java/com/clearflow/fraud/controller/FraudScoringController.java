package com.clearflow.fraud.controller;

import com.clearflow.fraud.domain.FraudRequest;
import com.clearflow.fraud.domain.FraudResponse;
import com.clearflow.fraud.service.FraudScoringService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Optional;

@RestController
@RequestMapping("/api/v1/fraud")
@Tag(name = "Fraud Scoring")
public class FraudScoringController {

    private final FraudScoringService fraudScoringService;
    private final StringRedisTemplate redisTemplate;

    public FraudScoringController(FraudScoringService fraudScoringService, StringRedisTemplate redisTemplate) {
        this.fraudScoringService = fraudScoringService;
        this.redisTemplate = redisTemplate;
    }

    @PostMapping("/score")
    @Operation(summary = "Score a payment using LightGBM model with resilience fallback")
    public ResponseEntity<FraudResponse> score(@RequestBody FraudRequest request) {
        return ResponseEntity.ok(fraudScoringService.score(request));
    }

    @GetMapping("/{paymentId}")
    @Operation(summary = "Retrieve cached fraud decision by payment identifier")
    public ResponseEntity<String> getScore(@PathVariable String paymentId) {
        return Optional.ofNullable(redisTemplate.opsForValue().get("fraud:score:" + paymentId))
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
