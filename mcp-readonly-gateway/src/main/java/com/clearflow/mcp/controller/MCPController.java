package com.clearflow.mcp.controller;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.clearflow.mcp.llm.LLMClient;
import com.clearflow.mcp.llm.LLMMessage;
import com.clearflow.mcp.service.AccessLogService;
import com.clearflow.mcp.service.ElasticsearchLogFetcher;
import com.clearflow.mcp.service.ForecastSettlementService;
import com.clearflow.mcp.service.McpMetricsService;
import com.clearflow.mcp.service.McpRateLimiter;
import com.clearflow.mcp.service.PaymentTimelineReconstructor;
import com.clearflow.mcp.service.RootCauseAnalysisService;
import com.clearflow.mcp.service.SystemicFailureDetector;
import com.clearflow.mcp.service.UETRAnomalyService;
import com.clearflow.mcp.tool.MCPTool;
import org.springframework.data.redis.core.StringRedisTemplate;

@RestController
@RequestMapping("/mcp")
public class MCPController {

    private static final String SYSTEM_PROMPT = """
            You are ClearFlow AI, an intelligent assistant for the ClearFlow ISO 20022 payment orchestration platform.
            You help operators understand payment flows, fraud scores, AML compliance results, and rail routing decisions.
            Be concise, factual, and security-aware. Never reveal raw credentials, keys, or internal IPs.
            Respond in plain text. If payment context is provided below, use it to answer accurately.
            If the payment timeline shows BLOCKED or FAILED status, state that clearly.
            If a tool says "No fraud score data found" but the timeline shows BLOCKED, the payment was still blocked — say so based on the available timeline data.
            Never say "status not available" if any tool returned a timeline with an overallStatus value.
            """;

    private final McpRateLimiter rateLimiter;
    private final AccessLogService accessLogService;
    private final LLMClient llmClient;
    private final List<MCPTool> tools;
    private final RootCauseAnalysisService rootCauseService;
    private final SystemicFailureDetector systemicDetector;
    private final McpMetricsService mcpMetricsService;
    private final ElasticsearchLogFetcher logFetcher;
    private final PaymentTimelineReconstructor timelineReconstructor;
    private final StringRedisTemplate redisTemplate;
    private final UETRAnomalyService uetrAnomalyService;
    private final ForecastSettlementService forecastService;

    public MCPController(McpRateLimiter rateLimiter,
                         AccessLogService accessLogService,
                         LLMClient llmClient,
                         List<MCPTool> tools,
                         RootCauseAnalysisService rootCauseService,
                         SystemicFailureDetector systemicDetector,
                         McpMetricsService mcpMetricsService,
                         ElasticsearchLogFetcher logFetcher,
                         PaymentTimelineReconstructor timelineReconstructor,
                         StringRedisTemplate redisTemplate,
                         UETRAnomalyService uetrAnomalyService,
                         ForecastSettlementService forecastService) {
        this.rateLimiter = rateLimiter;
        this.accessLogService = accessLogService;
        this.llmClient = llmClient;
        this.tools = tools;
        this.rootCauseService = rootCauseService;
        this.systemicDetector = systemicDetector;
        this.mcpMetricsService = mcpMetricsService;
        this.logFetcher = logFetcher;
        this.timelineReconstructor = timelineReconstructor;
        this.redisTemplate = redisTemplate;
        this.uetrAnomalyService = uetrAnomalyService;
        this.forecastService = forecastService;
    }

    /**
     * Root cause analysis — the flagship endpoint.
     * Fetches ES logs, reconstructs timeline, classifies failure, generates narrative.
     * Example: GET /mcp/payments/PAY-001/explain
     */
    @GetMapping("/payments/{paymentId}/explain")
    public ResponseEntity<?> explain(@PathVariable String paymentId, @AuthenticationPrincipal Jwt jwt) {
        String subject = subject(jwt);
        if (!rateLimiter.allow(subject)) {
            return ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS)
                    .body(Map.of("message", "Rate limit exceeded"));
        }
        accessLogService.log(paymentId, subject, "/mcp/payments/{paymentId}/explain");
        return ResponseEntity.ok(rootCauseService.explain(paymentId));
    }

    /**
     * Systemic failure detection — aggregated cross-payment health check.
     * Example: GET /mcp/diagnostics/systemic?windowMinutes=15
     */
    @GetMapping("/diagnostics/systemic")
    public ResponseEntity<?> systemic(
            @RequestParam(defaultValue = "15") int windowMinutes,
            @AuthenticationPrincipal Jwt jwt) {
        String subject = subject(jwt);
        if (!rateLimiter.allow(subject)) {
            return ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS)
                    .body(Map.of("message", "Rate limit exceeded"));
        }
        accessLogService.log("systemic", subject, "/mcp/diagnostics/systemic");
        return ResponseEntity.ok(systemicDetector.detect(windowMinutes));
    }

    private static final Map<String, Integer> SERVICE_PORTS = Map.of(
            "Gateway", 8080, "Fraud Scoring", 8081, "Validation", 8082,
            "AML Compliance", 8083, "Routing", 8084, "Settlement", 8085,
            "Audit", 8086, "MCP AI Gateway", 8087
    );

    /** GET /mcp/diagnostics/health-summary — probes all 8 services via TCP connect and returns compact status map. */
    @GetMapping("/diagnostics/health-summary")
    public ResponseEntity<?> healthSummary(@AuthenticationPrincipal Jwt jwt) {
        Map<String, String> result = new LinkedHashMap<>();
        SERVICE_PORTS.forEach((name, port) -> {
            try (java.net.Socket s = new java.net.Socket()) {
                s.connect(new java.net.InetSocketAddress("127.0.0.1", port), 1500);
                result.put(name, "UP");
            } catch (Exception e) {
                result.put(name, "DOWN");
            }
        });
        return ResponseEntity.ok(result);
    }

    /**
     * Active HIGH alerts in the last N minutes, grouped by service.
     * Example: GET /mcp/alerts/active?windowMinutes=30
     */
    @GetMapping("/alerts/active")
    public ResponseEntity<?> alerts(
            @RequestParam(defaultValue = "30") int windowMinutes,
            @AuthenticationPrincipal Jwt jwt) {
        String subject = subject(jwt);
        if (!rateLimiter.allow(subject)) {
            return ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS)
                    .body(Map.of("message", "Rate limit exceeded"));
        }
        accessLogService.log("alerts", subject, "/mcp/alerts/active");
        return ResponseEntity.ok(Map.of(
                "windowMinutes", windowMinutes,
                "alertsByService", rootCauseService != null
                        ? systemicDetector.detect(windowMinutes).alertsByService()
                        : Map.of()
        ));
    }

    @GetMapping("/payments/{paymentId}/timeline")
    public ResponseEntity<?> timeline(@PathVariable String paymentId, @AuthenticationPrincipal Jwt jwt) {
        String subject = subject(jwt);
        if (!rateLimiter.allow(subject)) {
            return ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS).body(Map.of("message", "Rate limit exceeded"));
        }
        accessLogService.log(paymentId, subject, "/mcp/payments/{paymentId}/timeline");
        var logs = logFetcher.fetchLogsForPayment(paymentId);
        var timeline = timelineReconstructor.reconstruct(paymentId, logs);
        return ResponseEntity.ok(timeline);
    }

    @GetMapping("/payments/{paymentId}/risk")
    public ResponseEntity<?> risk(@PathVariable String paymentId, @AuthenticationPrincipal Jwt jwt) {
        String subject = subject(jwt);
        if (!rateLimiter.allow(subject)) {
            return ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS).body(Map.of("message", "Rate limit exceeded"));
        }
        accessLogService.log(paymentId, subject, "/mcp/payments/{paymentId}/risk");
        // Pull fraud score from Redis cache (written by fraud-scoring service)
        String fraudJson = redisTemplate.opsForValue().get("fraud:score:" + paymentId);
        // Pull fraud log entries from ES
        var fraudLogs = logFetcher.fetchLogsForPayment(paymentId).stream()
                .filter(e -> "fraud-scoring".equals(e.service()))
                .toList();
        var result = new java.util.LinkedHashMap<String, Object>();
        result.put("paymentId", paymentId);
        result.put("fraudCacheEntry", fraudJson);
        result.put("fraudEvents", fraudLogs.stream().map(e -> Map.of(
                "timestamp", e.timestamp() != null ? e.timestamp() : "",
                "message", e.message() != null ? e.message() : "",
                "fraudScore", e.fraudScore() != null ? e.fraudScore() : "",
                "riskBand", e.riskBand() != null ? e.riskBand() : ""
        )).toList());
        return ResponseEntity.ok(result);
    }

    @GetMapping("/payments/{paymentId}/compliance")
    public ResponseEntity<?> compliance(@PathVariable String paymentId, @AuthenticationPrincipal Jwt jwt) {
        String subject = subject(jwt);
        if (!rateLimiter.allow(subject)) {
            return ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS).body(Map.of("message", "Rate limit exceeded"));
        }
        accessLogService.log(paymentId, subject, "/mcp/payments/{paymentId}/compliance");
        var amlLogs = logFetcher.fetchLogsForPayment(paymentId).stream()
                .filter(e -> "aml-compliance".equals(e.service()))
                .toList();
        var result = new java.util.LinkedHashMap<String, Object>();
        result.put("paymentId", paymentId);
        result.put("amlEvents", amlLogs.stream().map(e -> Map.of(
                "timestamp", e.timestamp() != null ? e.timestamp() : "",
                "message", e.message() != null ? e.message() : "",
                "screeningResult", e.screeningResult() != null ? e.screeningResult() : "",
                "matchScore", e.matchScore() != null ? e.matchScore() : "",
                "listHit", e.listHit() != null ? e.listHit() : ""
        )).toList());
        return ResponseEntity.ok(result);
    }

    @GetMapping("/metrics/rails")
    public ResponseEntity<?> rails(@AuthenticationPrincipal Jwt jwt) {
        String subject = subject(jwt);
        if (!rateLimiter.allow(subject)) {
            return ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS).body(Map.of("message", "Rate limit exceeded"));
        }
        accessLogService.log("metrics", subject, "/mcp/metrics/rails");
        return ResponseEntity.ok(mcpMetricsService.railDistribution(24 * 60));
    }

    @GetMapping("/metrics/fraud")
    public ResponseEntity<?> fraud(@AuthenticationPrincipal Jwt jwt) {
        String subject = subject(jwt);
        if (!rateLimiter.allow(subject)) {
            return ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS).body(Map.of("message", "Rate limit exceeded"));
        }
        accessLogService.log("metrics", subject, "/mcp/metrics/fraud");
        return ResponseEntity.ok(mcpMetricsService.fraudHistogram(24 * 60));
    }

    @GetMapping("/metrics/overview")
    public ResponseEntity<?> overview(@AuthenticationPrincipal Jwt jwt) {
        String subject = subject(jwt);
        if (!rateLimiter.allow(subject)) {
            return ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS).body(Map.of("message", "Rate limit exceeded"));
        }
        accessLogService.log("metrics", subject, "/mcp/metrics/overview");
        return ResponseEntity.ok(mcpMetricsService.overview(24 * 60));
    }

    @PostMapping("/chat")
    public ResponseEntity<?> chat(@RequestBody ChatRequest req, @AuthenticationPrincipal Jwt jwt) {
        String subject = subject(jwt);
        if (!rateLimiter.allow(subject)) {
            return ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS)
                    .body(Map.of("message", "Rate limit exceeded"));
        }

        StringBuilder context = new StringBuilder();
        if (req.paymentId() != null && !req.paymentId().isBlank()) {
            Map<String, Object> toolInput = Map.of("paymentId", req.paymentId());
            for (MCPTool tool : tools) {
                Object result = tool.execute(toolInput);
                context.append(tool.name()).append(": ").append(result).append("\n");
            }
            accessLogService.log(req.paymentId(), subject(jwt), "/mcp/chat");
        }

        List<LLMMessage> messages = new ArrayList<>();
        String systemContent = SYSTEM_PROMPT + (context.isEmpty() ? "" : "\nPayment context:\n" + context);
        messages.add(new LLMMessage("system", systemContent));
        if (req.history() != null) {
            messages.addAll(req.history());
        }
        messages.add(new LLMMessage("user", req.question()));

        String answer = llmClient.chat(messages);
        return ResponseEntity.ok(Map.of(
                "answer", answer,
                "provider", llmClient.providerName()
        ));
    }

    /**
     * UETR velocity anomaly detection — sliding-window z-score over debtor payment counts.
     * Example: GET /mcp/anomalies/uetr?windowMinutes=60
     */
    @GetMapping("/anomalies/uetr")
    public ResponseEntity<?> uetrAnomalies(
            @RequestParam(defaultValue = "60") int windowMinutes,
            @AuthenticationPrincipal Jwt jwt) {
        String subject = subject(jwt);
        if (!rateLimiter.allow(subject)) {
            return ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS)
                    .body(Map.of("message", "Rate limit exceeded"));
        }
        accessLogService.log("uetr-anomaly", subject, "/mcp/anomalies/uetr");
        return ResponseEntity.ok(uetrAnomalyService.detect(windowMinutes));
    }

    /**
     * Settlement volume forecasting — exponential smoothing over ES hourly counts.
     * Example: GET /mcp/forecast/settlement?horizonHours=24
     */
    @GetMapping("/forecast/settlement")
    public ResponseEntity<?> forecastSettlement(
            @RequestParam(defaultValue = "24") int horizonHours,
            @AuthenticationPrincipal Jwt jwt) {
        String subject = subject(jwt);
        if (!rateLimiter.allow(subject)) {
            return ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS)
                    .body(Map.of("message", "Rate limit exceeded"));
        }
        accessLogService.log("settlement-forecast", subject, "/mcp/forecast/settlement");
        return ResponseEntity.ok(forecastService.forecast(horizonHours));
    }

    private ResponseEntity<?> guarded(String paymentId, Jwt jwt, String path, Object payload) {
        String subject = subject(jwt);
        if (!rateLimiter.allow(subject)) {
            return ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS)
                    .body(Map.of("message", "Rate limit exceeded"));
        }
        accessLogService.log(paymentId, subject, path);
        return ResponseEntity.ok(payload);
    }

    private static String subject(Jwt jwt) {
        return jwt != null ? jwt.getSubject() : "anonymous";
    }
}
