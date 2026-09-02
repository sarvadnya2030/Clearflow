package com.clearflow.mcp.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.*;

/**
 * Phase 4 feature: Predictive cascade simulation.
 * Answers: "If service X fails, what's the impact?"
 *
 * Simulates failure propagation through the payment pipeline to forecast
 * the cascading impact on downstream services.
 */
@Service
public class PredictiveCascadeSimulator {

    private static final Logger log = LoggerFactory.getLogger(PredictiveCascadeSimulator.class);

    // Pipeline: gateway (0) → fraud (1) → validation (2) → aml (3) → routing (4) → settlement (5) → audit (6)
    private static final Map<Integer, List<Integer>> DOWNSTREAM_SERVICES = Map.ofEntries(
        Map.entry(0, List.of(1, 2, 3, 4, 5, 6)),     // gateway → all
        Map.entry(1, List.of(2, 3, 4, 5, 6)),        // fraud → validation, aml, routing, settlement, audit
        Map.entry(2, List.of(3, 4, 5, 6)),           // validation → aml, routing, settlement, audit
        Map.entry(3, List.of(4, 5, 6)),              // aml → routing, settlement, audit
        Map.entry(4, List.of(5, 6)),                 // routing → settlement, audit
        Map.entry(5, List.of(6)),                    // settlement → audit
        Map.entry(6, List.of())                      // audit → nothing
    );

    private static final String[] SERVICE_NAMES = {
        "gateway", "fraud-scoring", "validation-enrichment", "aml-compliance",
        "routing-execution", "settlement", "audit"
    };

    private static final int[] BASE_LATENCY_MS = { 10, 50, 30, 80, 60, 40, 20 };

    public record SimulationResult(
        String failedService,
        int affectedPayments,
        List<String> affectedServices,
        double estimatedLatencyIncrease,
        double estimatedThroughputDrop,
        String recommendedMitigation
    ) {}

    /**
     * Simulate cascade if a specific service fails.
     *
     * @param serviceIndex 0-6 (gateway to audit)
     * @param durationSeconds How long the service is down
     * @return Impact assessment
     */
    public SimulationResult simulateServiceFailure(int serviceIndex, int durationSeconds) {
        if (serviceIndex < 0 || serviceIndex >= SERVICE_NAMES.length) {
            throw new IllegalArgumentException("Invalid service index: " + serviceIndex);
        }

        String failedService = SERVICE_NAMES[serviceIndex];
        List<Integer> downstream = DOWNSTREAM_SERVICES.getOrDefault(serviceIndex, List.of());
        List<String> affectedServiceNames = new ArrayList<>();

        for (int idx : downstream) {
            affectedServiceNames.add(SERVICE_NAMES[idx]);
        }

        // Estimate impact
        double latencyIncrease = calculateLatencyImpact(serviceIndex, durationSeconds);
        double throughputDrop = calculateThroughputDrop(serviceIndex, downstream.size());
        int affectedPayments = estimateAffectedPayments(durationSeconds, throughputDrop);
        String mitigation = recommendMitigation(serviceIndex, failedService);

        log.info("Simulated failure of {} for {}s: {:.1f}% latency increase, {:.1f}% throughput drop, {} payments affected",
            failedService, durationSeconds, latencyIncrease, throughputDrop, affectedPayments);

        return new SimulationResult(
            failedService,
            affectedPayments,
            affectedServiceNames,
            latencyIncrease,
            throughputDrop,
            mitigation
        );
    }

    /**
     * Estimate latency impact.
     */
    private double calculateLatencyImpact(int serviceIndex, int durationSeconds) {
        // Service timeout causes queue buildup
        // P99 latency increases quadratically with queue depth
        int queueDepth = (int) (100 * durationSeconds / 10.0);  // ~10 payments/sec
        return Math.min(100, queueDepth * 0.5);  // Capped at 100% increase
    }

    /**
     * Estimate throughput drop.
     */
    private double calculateThroughputDrop(int serviceIndex, int affectedServiceCount) {
        // Each failed service stage blocks downstream
        // Gateway failure = 100% drop, later stages = less impact
        return 100.0 * (7 - serviceIndex) / 7.0 * (1 + affectedServiceCount * 0.1);
    }

    /**
     * Estimate affected payments.
     */
    private int estimateAffectedPayments(int durationSeconds, double throughputDropPercent) {
        double avgPaymentsPerSecond = 90;  // From 100K test: 100K/1110s ≈ 90/s
        return (int) (avgPaymentsPerSecond * durationSeconds * throughputDropPercent / 100);
    }

    /**
     * Recommend mitigation strategy.
     */
    private String recommendMitigation(int serviceIndex, String serviceName) {
        return switch (serviceIndex) {
            case 0 -> "CRITICAL: Restart gateway immediately. Failover to secondary region if available.";
            case 1 -> "HIGH: Disable fraud scoring (default to LOW risk) or use fallback model.";
            case 2 -> "HIGH: Skip validation enrichment, use cached enrichment data.";
            case 3 -> "CRITICAL: Disable AML screening or use accelerated mode (sample 1/10 payments).";
            case 4 -> "CRITICAL: Failover to backup rails or delay routing.";
            case 5 -> "HIGH: Queue settlements, process after service recovery.";
            case 6 -> "LOW: Skip audit logging temporarily, catch up later.";
            default -> "UNKNOWN: Investigate service logs.";
        };
    }

    /**
     * Simulate multiple sequential failures (chain reaction).
     */
    public List<SimulationResult> simulateChainReaction(int initialServiceIndex) {
        List<SimulationResult> results = new ArrayList<>();

        int currentService = initialServiceIndex;
        int remainingServices = 7 - initialServiceIndex;

        for (int i = 0; i < remainingServices; i++) {
            SimulationResult result = simulateServiceFailure(currentService, 60);  // 60 second baseline
            results.add(result);

            // Cascade: if this service fails, downstream likely fails too (50% probability)
            if (Math.random() < 0.5 && currentService < 6) {
                currentService++;
            }
        }

        return results;
    }

    /**
     * Calculate MTTR (Mean Time To Recovery) impact.
     */
    public int estimateMTTR(int serviceIndex) {
        // Based on historical SLAs
        return switch (serviceIndex) {
            case 0 -> 15;  // gateway: 15 min
            case 1 -> 10;  // fraud: 10 min
            case 2 -> 8;   // validation: 8 min
            case 3 -> 20;  // aml: 20 min (compliance constraints)
            case 4 -> 15;  // routing: 15 min
            case 5 -> 10;  // settlement: 10 min
            case 6 -> 5;   // audit: 5 min
            default -> 0;
        };
    }

    /**
     * Cost impact estimate (assumes $X per failed payment).
     */
    public double estimateCostImpact(int serviceIndex, int durationSeconds) {
        SimulationResult sim = simulateServiceFailure(serviceIndex, durationSeconds);
        double costPerFailedPayment = 5.0;  // SLA penalty, ops overhead, etc.
        return sim.affectedPayments() * costPerFailedPayment;
    }
}
