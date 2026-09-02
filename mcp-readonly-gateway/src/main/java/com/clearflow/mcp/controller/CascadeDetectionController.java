package com.clearflow.mcp.controller;

import com.clearflow.mcp.service.CascadeFailureDetector;
import com.clearflow.mcp.service.CascadeFailureDetector.CascadePattern;
import com.clearflow.mcp.service.CodeGraphService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;

/**
 * Production REST API for cascade failure detection.
 * Provides HTTP endpoints + Server-Sent Events (SSE) streaming.
 */
@RestController
@RequestMapping("/mcp/cascade")
public class CascadeDetectionController {

    private static final Logger log = LoggerFactory.getLogger(CascadeDetectionController.class);

    private final CascadeFailureDetector detector;
    private final CodeGraphService codeGraphService;
    private final List<SseEmitter> emitters = new CopyOnWriteArrayList<>();

    public CascadeDetectionController(CascadeFailureDetector detector, CodeGraphService codeGraphService) {
        this.detector = detector;
        this.codeGraphService = codeGraphService;
    }

    /**
     * Standing verification endpoint, not throwaway: dumps exactly what
     * every internal evidence source actually returns for a given service,
     * so any future change to the graph/context pipeline can be checked
     * by direct inspection rather than trusted because a caller endpoint
     * didn't error. Built after finding CodeGraphService.getCodeContext had
     * been silently returning empty context for every real service all
     * session (deriveModule bug, fixed in v41) -- an LLM call returning
     * HTTP 200 with a plausible-looking answer is NOT evidence its inputs
     * were real; this endpoint is how to check.
     * Usage: GET /mcp/cascade/debug-evidence?service=aml-compliance&failureType=AML_SANCTIONS_HIT
     */
    @GetMapping("/debug-evidence")
    public ResponseEntity<?> debugEvidence(
            @RequestParam String service,
            @RequestParam(required = false) String failureType) {
        return ResponseEntity.ok(Map.of(
                "codeContext", codeGraphService.getCodeContext(service, failureType),
                "brokerContext", codeGraphService.getBrokerContext(service, failureType),
                "moduleGraph", codeGraphService.getModuleGraph(),
                "coverage", codeGraphService.getCoverage(),
                "codeGraphLoaded", codeGraphService.isLoaded(),
                "topologyLoaded", codeGraphService.isTopologyLoaded()
        ));
    }

    /**
     * Real-time root-cause diagnosis via z-score + topology tie-break --
     * see CascadeFailureDetector.diagnoseByZScore()'s docstring for why this
     * exists alongside (not instead of) /detect, which structurally never
     * fires against this project's real fault types.
     * Usage: GET /mcp/cascade/diagnose?windowMinutes=1&lookbackHours=0.05
     */
    @GetMapping("/diagnose")
    public ResponseEntity<?> diagnose(
            @RequestParam(defaultValue = "1") int windowMinutes,
            @RequestParam(defaultValue = "0.05") double lookbackHours) {
        try {
            var diagnosis = detector.diagnoseByZScore(windowMinutes, lookbackHours);
            return ResponseEntity.ok(diagnosis);
        } catch (Exception ex) {
            log.error("diagnose failed", ex);
            return ResponseEntity.internalServerError().body(Map.of("error", ex.getMessage()));
        }
    }

    /**
     * Diagnose a specific PAST incident by its exact window -- used by
     * eval_harness.py's mcp_rca_baseline to score MCP's own live diagnosis
     * against real historical incidents, the same way every other method
     * in this project is scored.
     * Usage: GET /mcp/cascade/diagnose-range?windowStartMs=...&windowEndMs=...&lookbackHours=0.05
     */
    @GetMapping("/diagnose-range")
    public ResponseEntity<?> diagnoseRange(
            @RequestParam long windowStartMs,
            @RequestParam long windowEndMs,
            @RequestParam(defaultValue = "0.05") double lookbackHours) {
        try {
            var diagnosis = detector.diagnoseByZScoreForRange(windowStartMs, windowEndMs, lookbackHours);
            return ResponseEntity.ok(diagnosis);
        } catch (Exception ex) {
            log.error("diagnose-range failed", ex);
            return ResponseEntity.internalServerError().body(Map.of("error", ex.getMessage()));
        }
    }

    /**
     * Real LLM-augmented diagnosis: genuine model call (openai/gpt-oss-20b
     * via NVIDIA NIM, matching eval_harness.py's validated LLM baselines),
     * given real z-scores, real payment-state fracs, real sample log lines,
     * and real source-code context from CodeGraphService -- not simulated.
     * Usage: GET /mcp/cascade/diagnose-llm?windowStartMs=...&windowEndMs=...&lookbackHours=0.05
     */
    @GetMapping("/diagnose-llm")
    public ResponseEntity<?> diagnoseLlm(
            @RequestParam long windowStartMs,
            @RequestParam long windowEndMs,
            @RequestParam(defaultValue = "0.05") double lookbackHours) {
        try {
            var diagnosis = detector.diagnoseWithLLM(windowStartMs, windowEndMs, lookbackHours);
            return ResponseEntity.ok(diagnosis);
        } catch (Exception ex) {
            log.error("diagnose-llm failed", ex);
            return ResponseEntity.internalServerError().body(Map.of("error", ex.getMessage()));
        }
    }

    /**
     * Real graph-RAG diagnosis: real payment-state fracs (proven override
     * signal, unchanged) falling back to real multi-hop blast-radius
     * traversal over graph.json's actual code edges instead of a flat
     * topology tie-break -- see CascadeFailureDetector.diagnoseByGraphRagForRange.
     * Usage: GET /mcp/cascade/diagnose-graphrag?windowStartMs=...&windowEndMs=...&lookbackHours=0.05
     */
    @GetMapping("/diagnose-graphrag")
    public ResponseEntity<?> diagnoseGraphRag(
            @RequestParam long windowStartMs,
            @RequestParam long windowEndMs,
            @RequestParam(defaultValue = "0.05") double lookbackHours) {
        try {
            var diagnosis = detector.diagnoseByGraphRagForRange(windowStartMs, windowEndMs, lookbackHours);
            return ResponseEntity.ok(diagnosis);
        } catch (Exception ex) {
            log.error("diagnose-graphrag failed", ex);
            return ResponseEntity.internalServerError().body(Map.of("error", ex.getMessage()));
        }
    }

    /**
     * Real SLM-augmented diagnosis: same real evidence and prompt as
     * /diagnose-llm, routed to a genuine local Ollama model (qwen3:4b, real
     * weights on this machine) instead of the cloud NVIDIA path -- a fair
     * apples-to-apples SLM-vs-LLM comparison for eval_harness.py.
     * Usage: GET /mcp/cascade/diagnose-slm?windowStartMs=...&windowEndMs=...&lookbackHours=0.05
     */
    @GetMapping("/diagnose-slm")
    public ResponseEntity<?> diagnoseSlm(
            @RequestParam long windowStartMs,
            @RequestParam long windowEndMs,
            @RequestParam(defaultValue = "0.05") double lookbackHours) {
        try {
            var diagnosis = detector.diagnoseWithSLM(windowStartMs, windowEndMs, lookbackHours);
            return ResponseEntity.ok(diagnosis);
        } catch (Exception ex) {
            log.error("diagnose-slm failed", ex);
            return ResponseEntity.internalServerError().body(Map.of("error", ex.getMessage()));
        }
    }

    /**
     * Detect cascades in last N minutes (REST endpoint).
     * Usage: GET /mcp/cascade/detect?minutes=5
     */
    @GetMapping("/detect")
    public ResponseEntity<?> detectCascades(
        @RequestParam(defaultValue = "5") int minutes) {

        try {
            List<CascadePattern> cascades = detector.detectActiveCascades(minutes);

            return ResponseEntity.ok(Map.of(
                "timestamp", System.currentTimeMillis(),
                "window_minutes", minutes,
                "cascades_detected", cascades.size(),
                "cascades", cascades,
                "cache_size", detector.getRecentCascades().size()
            ));

        } catch (Exception ex) {
            log.error("Failed to detect cascades", ex);
            return ResponseEntity.status(500).body(Map.of(
                "error", ex.getMessage(),
                "timestamp", System.currentTimeMillis()
            ));
        }
    }

    /**
     * Get cached cascades (no ES query, instant response).
     * Usage: GET /mcp/cascade/recent
     */
    @GetMapping("/recent")
    public ResponseEntity<?> getRecentCascades() {
        List<CascadePattern> cascades = detector.getRecentCascades();

        return ResponseEntity.ok(Map.of(
            "timestamp", System.currentTimeMillis(),
            "cascades", cascades,
            "count", cascades.size()
        ));
    }

    /**
     * Stream cascade alerts in real-time (SSE).
     * Usage: EventSource.addEventListener("cascade", handler)
     */
    @GetMapping(value = "/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter streamCascadeAlerts() {
        SseEmitter emitter = new SseEmitter(30000L);  // 30 second timeout
        emitters.add(emitter);

        emitter.onCompletion(() -> {
            emitters.remove(emitter);
            log.debug("SSE client disconnected");
        });
        emitter.onTimeout(() -> {
            emitters.remove(emitter);
            log.debug("SSE client timeout");
        });

        try {
            // Send initial connection message
            emitter.send(SseEmitter.event()
                .name("connected")
                .data(Map.of("status", "connected", "timestamp", System.currentTimeMillis()))
                .id(String.valueOf(System.nanoTime()))
                .reconnectTime(5000)
            );
        } catch (IOException ex) {
            log.debug("Failed to send initial SSE message", ex);
            emitters.remove(emitter);
        }

        return emitter;
    }

    /**
     * Broadcast cascade alert to all connected SSE clients.
     * Called by the monitoring service when a cascade is detected.
     */
    public void broadcastCascadeAlert(CascadePattern cascade) {
        String alert = detector.generateAlert(cascade);

        List<SseEmitter> deadEmitters = new ArrayList<>();

        for (SseEmitter emitter : emitters) {
            try {
                emitter.send(SseEmitter.event()
                    .name("cascade")
                    .data(Map.of(
                        "id", cascade.id(),
                        "root_cause", cascade.rootCauseService(),
                        "type", cascade.cascadeType(),
                        "severity", cascade.severity(),
                        "affected_services", cascade.propagationChain().size(),
                        "propagation_speed_ms", String.format("%.1f", cascade.propagationSpeed()),
                        "alert", alert,
                        "timestamp", System.currentTimeMillis()
                    ))
                    .id(cascade.id())
                    .reconnectTime(5000)
                );
            } catch (IOException ex) {
                log.debug("Failed to send SSE alert, marking emitter as dead", ex);
                deadEmitters.add(emitter);
            }
        }

        deadEmitters.forEach(emitters::remove);
    }

    /**
     * Manual check for cascades (polling endpoint).
     * Returns paginated cascade details with full chain.
     * Usage: GET /mcp/cascade/check?minutes=10&severity=CRITICAL
     */
    @GetMapping("/check")
    public ResponseEntity<?> checkCascades(
        @RequestParam(defaultValue = "10") int minutes,
        @RequestParam(required = false) String severity) {

        try {
            List<CascadePattern> cascades = detector.detectActiveCascades(minutes);

            if (severity != null && !severity.isEmpty()) {
                cascades = cascades.stream()
                    .filter(c -> c.severity().equals(severity))
                    .toList();
            }

            return ResponseEntity.ok(Map.of(
                "status", "ok",
                "cascades_found", cascades.size(),
                "window_minutes", minutes,
                "filter_severity", severity != null ? severity : "any",
                "results", cascades.stream()
                    .map(c -> Map.of(
                        "id", c.id(),
                        "root_cause", c.rootCauseService(),
                        "cascade_type", c.cascadeType(),
                        "severity", c.severity(),
                        "affected_services", c.propagationChain().size(),
                        "propagation_speed_ms", String.format("%.1f", c.propagationSpeed()),
                        "services_chain", c.propagationChain().stream()
                            .map(e -> e.service() + "[" + e.stageNumber() + "]")
                            .toList()
                    ))
                    .toList(),
                "timestamp", System.currentTimeMillis()
            ));

        } catch (Exception ex) {
            log.error("Failed to check cascades", ex);
            return ResponseEntity.status(500).body(Map.of(
                "error", "Cascade detection failed",
                "reason", ex.getMessage()
            ));
        }
    }
}
