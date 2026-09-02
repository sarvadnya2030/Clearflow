package com.clearflow.mcp.controller;

import com.clearflow.mcp.service.PredictiveCascadeSimulator;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * Phase 4 REST API: Predictive cascade simulation.
 * Answers: "If service X fails, what's the impact?"
 */
@RestController
@RequestMapping("/mcp/predictive")
public class PredictiveController {

    private static final Logger log = LoggerFactory.getLogger(PredictiveController.class);

    private final PredictiveCascadeSimulator simulator;

    public PredictiveController(PredictiveCascadeSimulator simulator) {
        this.simulator = simulator;
    }

    /**
     * Simulate single service failure.
     * Usage: GET /mcp/predictive/simulate-failure?service=3&durationSeconds=60
     * Services: 0=gateway, 1=fraud, 2=validation, 3=aml, 4=routing, 5=settlement, 6=audit
     */
    @GetMapping("/simulate-failure")
    public ResponseEntity<?> simulateFailure(
        @RequestParam int service,
        @RequestParam(defaultValue = "60") int durationSeconds) {

        try {
            PredictiveCascadeSimulator.SimulationResult result =
                simulator.simulateServiceFailure(service, durationSeconds);

            return ResponseEntity.ok(Map.of(
                "timestamp", System.currentTimeMillis(),
                "simulation", result,
                "mttr_minutes", simulator.estimateMTTR(service),
                "cost_impact_usd", String.format("$%.2f", simulator.estimateCostImpact(service, durationSeconds))
            ));
        } catch (Exception ex) {
            log.error("Simulation failed", ex);
            return ResponseEntity.status(400).body(Map.of(
                "error", ex.getMessage()
            ));
        }
    }

    /**
     * Simulate chain reaction (multiple cascading failures).
     * Usage: GET /mcp/predictive/simulate-chain?startService=3
     */
    @GetMapping("/simulate-chain")
    public ResponseEntity<?> simulateChain(
        @RequestParam int startService) {

        try {
            List<PredictiveCascadeSimulator.SimulationResult> results =
                simulator.simulateChainReaction(startService);

            return ResponseEntity.ok(Map.of(
                "timestamp", System.currentTimeMillis(),
                "chain_length", results.size(),
                "results", results
            ));
        } catch (Exception ex) {
            log.error("Chain simulation failed", ex);
            return ResponseEntity.status(400).body(Map.of(
                "error", ex.getMessage()
            ));
        }
    }

    /**
     * Get impact summary for all services.
     * Usage: GET /mcp/predictive/impact-summary?durationSeconds=60
     */
    @GetMapping("/impact-summary")
    public ResponseEntity<?> getImpactSummary(
        @RequestParam(defaultValue = "60") int durationSeconds) {

        try {
            Map<String, Object> impactByService = Map.ofEntries(
                Map.entry("gateway", simulator.simulateServiceFailure(0, durationSeconds)),
                Map.entry("fraud-scoring", simulator.simulateServiceFailure(1, durationSeconds)),
                Map.entry("validation", simulator.simulateServiceFailure(2, durationSeconds)),
                Map.entry("aml-compliance", simulator.simulateServiceFailure(3, durationSeconds)),
                Map.entry("routing-execution", simulator.simulateServiceFailure(4, durationSeconds)),
                Map.entry("settlement", simulator.simulateServiceFailure(5, durationSeconds)),
                Map.entry("audit", simulator.simulateServiceFailure(6, durationSeconds))
            );

            return ResponseEntity.ok(Map.of(
                "timestamp", System.currentTimeMillis(),
                "duration_seconds", durationSeconds,
                "impact_by_service", impactByService
            ));
        } catch (Exception ex) {
            return ResponseEntity.status(400).body(Map.of("error", ex.getMessage()));
        }
    }
}
