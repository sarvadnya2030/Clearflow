package com.clearflow.fraud.service;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import io.github.resilience4j.reactor.circuitbreaker.operator.CircuitBreakerOperator;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

import java.time.Duration;
import java.util.Map;

@Component
public class LightGBMStubClient {

    private final WebClient webClient;
    private final CircuitBreaker circuitBreaker;

    public LightGBMStubClient(WebClient.Builder builder,
                               CircuitBreakerRegistry circuitBreakerRegistry,
                               @Value("${fraud.model-server-url:http://localhost:8091}") String baseUrl) {
        this.webClient      = builder.baseUrl(baseUrl).build();
        this.circuitBreaker = circuitBreakerRegistry.circuitBreaker("lgbm");
    }

    public Mono<ModelScoreResponse> predict(double[] features, Map<String, Object> metadata) {
        return webClient.post()
                .uri("/predict")
                .bodyValue(Map.of("features", features, "metadata", metadata))
                .retrieve()
                .bodyToMono(ModelScoreResponse.class)
                .retryWhen(Retry.fixedDelay(2, Duration.ofMillis(200)))
                .transformDeferred(CircuitBreakerOperator.of(circuitBreaker))
                .onErrorResume(throwable -> Mono.just(
                        new ModelScoreResponse(0.55d, Map.of("fallback", 1.0d), "fallback-cb")));
    }

    public record ModelScoreResponse(double score, Map<String, Double> featureImportance, String modelVersion) {
    }
}
