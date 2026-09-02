package com.clearflow.fraud.service;

import com.clearflow.fraud.domain.FraudRequest;
import com.clearflow.fraud.domain.FraudResponse;
import com.clearflow.fraud.domain.RiskBand;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.stereotype.Service;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

@Service
public class FraudScoringService {

    private static final Logger log = LoggerFactory.getLogger(FraudScoringService.class);

    private final FeatureEngineeringService featureEngineeringService;
    private final LightGBMStubClient lightGBMStubClient;
    private final HeuristicScoringService heuristicScoringService;
    private final MeterRegistry meterRegistry;
    private final AtomicReference<Double> lastFraudScore = new AtomicReference<>(0.0);

    public FraudScoringService(FeatureEngineeringService featureEngineeringService,
                               LightGBMStubClient lightGBMStubClient,
                               HeuristicScoringService heuristicScoringService,
                               MeterRegistry meterRegistry) {
        this.featureEngineeringService = featureEngineeringService;
        this.lightGBMStubClient = lightGBMStubClient;
        this.heuristicScoringService = heuristicScoringService;
        this.meterRegistry = meterRegistry;
        io.micrometer.core.instrument.Gauge.builder("clearflow_fraud_score_current", lastFraudScore, AtomicReference::get)
                .tag("service", "fraud-scoring")
                .description("Most recent fraud score computed")
                .register(meterRegistry);
    }

    public FraudResponse score(FraudRequest request) {
        long start = System.currentTimeMillis();
        double[] features = featureEngineeringService.extractFeatures(request);
        List<String> featureNames = featureEngineeringService.featureNames();

        LightGBMStubClient.ModelScoreResponse modelResponse;
        try {
            modelResponse = lightGBMStubClient
                    .predict(features, Map.of("paymentId", request.paymentId(), "currency", request.currency()))
                    .blockOptional()
                    .orElse(null);
        } catch (Exception e) {
            log.debug("Model server unavailable, using heuristic fallback for paymentId={}", request.paymentId());
            modelResponse = null;
        }

        FraudResponse response;
        if (modelResponse == null || "fallback-cb".equals(modelResponse.modelVersion())) {
            response = heuristicScoringService.heuristicScore(request, start);
        } else {
            Map<String, Double> explainability = new HashMap<>();
            if (modelResponse.featureImportance() != null && !modelResponse.featureImportance().isEmpty()) {
                explainability.putAll(modelResponse.featureImportance());
            } else {
                for (int i = 0; i < featureNames.size(); i++) {
                    explainability.put(featureNames.get(i), i < features.length ? features[i] : 0.0d);
                }
            }
            BigDecimal score = BigDecimal.valueOf(modelResponse.score()).setScale(4, RoundingMode.HALF_UP);
            response = new FraudResponse(
                    request.paymentId(),
                    score,
                    heuristicScoringService.toRiskBand(score),
                    explainability,
                    modelResponse.modelVersion(),
                    Instant.now(),
                    System.currentTimeMillis() - start,
                    false
            );
        }

        long durationMs = System.currentTimeMillis() - start;
        lastFraudScore.set(response.fraudScore().doubleValue());
        Counter.builder("clearflow_payments_total")
                .tag("service", "fraud-scoring")
                .tag("riskBand", response.riskBand().name())
                .tag("fallback", String.valueOf(response.fallbackUsed()))
                .description("Total payments scored by fraud engine")
                .register(meterRegistry)
                .increment();
        meterRegistry.timer("clearflow_processing_duration", "service", "fraud-scoring", "stage", "scoring")
                .record(durationMs, java.util.concurrent.TimeUnit.MILLISECONDS);
        MDC.put("paymentId", request.paymentId());
        MDC.put("fraudScore", response.fraudScore().toPlainString());
        MDC.put("riskBand", response.riskBand().name());
        MDC.put("durationMs", String.valueOf(durationMs));
        try {
            if (response.riskBand() == RiskBand.CRITICAL || response.riskBand() == RiskBand.HIGH) {
                log.warn("FRAUD_SCORE_COMPUTED score={} riskBand={} paymentId={} durationMs={}",
                        response.fraudScore(), response.riskBand(), request.paymentId(), durationMs);
            } else {
                log.info("FRAUD_SCORE_COMPUTED score={} riskBand={} paymentId={} durationMs={}",
                        response.fraudScore(), response.riskBand(), request.paymentId(), durationMs);
            }
        } finally {
            MDC.remove("fraudScore");
            MDC.remove("riskBand");
            MDC.remove("durationMs");
        }
        return response;
    }
}
