package com.clearflow.mcp.service;

import com.clearflow.mcp.llm.LLMClient;
import com.clearflow.mcp.llm.LLMMessage;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Map;

/**
 * Detects cross-payment systemic failure patterns using ES aggregations.
 *
 * A systemic failure is not one payment failing — it's many payments failing
 * at the same stage simultaneously (infrastructure outage, config push gone wrong,
 * upstream dependency degraded).
 *
 * Uses ES terms aggregations rather than per-payment queries, so it operates
 * efficiently across thousands of events without pulling raw log data.
 */
@Service
public class SystemicFailureDetector {

    private static final Logger log = LoggerFactory.getLogger(SystemicFailureDetector.class);

    // Thresholds: tune per environment
    private static final int HIGH_ALERT_THRESHOLD = 5;   // ≥5 HIGH alerts in window → flag
    private static final int ERROR_LOG_THRESHOLD   = 10;  // ≥10 ERROR logs in window → flag

    public record SystemicReport(
            boolean isSystemic,
            List<String> affectedServices,
            Map<String, Long> alertsByService,
            Map<String, Long> errorsByService,
            String pattern,
            String severity,
            String suggestedAction,
            String llmNarrative,
            String llmProvider,
            int windowMinutes
    ) {}

    private final ElasticsearchLogFetcher logFetcher;
    private final LLMClient llmClient;
    private final ObjectMapper objectMapper;

    public SystemicFailureDetector(ElasticsearchLogFetcher logFetcher,
                                   LLMClient llmClient,
                                   ObjectMapper objectMapper) {
        this.logFetcher = logFetcher;
        this.llmClient = llmClient;
        this.objectMapper = objectMapper;
    }

    public SystemicReport detect(int windowMinutes) {
        // Fetch aggregated data from ES
        Map<String, Long> alertsByService = logFetcher.countAlertsByService(windowMinutes);
        Map<String, Long> errorsByService = logFetcher.countByEventType(null, windowMinutes);

        // Determine affected services (above threshold)
        List<String> affected = alertsByService.entrySet().stream()
                .filter(e -> e.getValue() >= HIGH_ALERT_THRESHOLD)
                .map(Map.Entry::getKey)
                .sorted()
                .toList();

        boolean isSystemic = !affected.isEmpty()
                || errorsByService.values().stream().anyMatch(c -> c >= ERROR_LOG_THRESHOLD);

        // Derive pattern and severity without LLM
        String pattern = derivePattern(affected, alertsByService, errorsByService);
        String severity = deriveSeverity(affected.size(), alertsByService, errorsByService);

        // LLM narrative for the systemic report
        String llmNarrative = null;
        String llmProvider = llmClient.providerName();
        if (isSystemic) {
            try {
                String raw = llmClient.chat(List.of(
                        new LLMMessage("system", PromptTemplates.systemicSystem()),
                        new LLMMessage("user", PromptTemplates.systemicUser(
                                alertsByService, errorsByService, windowMinutes))
                ));
                llmNarrative = extractNarrative(raw);
            } catch (Exception e) {
                log.warn("LLM systemic analysis failed: {}", e.getMessage());
            }
        }

        String suggestedAction = suggestedAction(affected, isSystemic);

        log.info("Systemic detection complete — windowMinutes={} isSystemic={} affected={}",
                windowMinutes, isSystemic, affected);

        return new SystemicReport(
                isSystemic, affected, alertsByService, errorsByService,
                pattern, severity, suggestedAction, llmNarrative, llmProvider, windowMinutes
        );
    }

    // ── Rule-based pattern derivation ─────────────────────────────────────────

    private String derivePattern(List<String> affected,
                                 Map<String, Long> alerts,
                                 Map<String, Long> errors) {
        if (affected.isEmpty() && errors.values().stream().allMatch(c -> c < ERROR_LOG_THRESHOLD)) {
            return "No systemic pattern detected";
        }
        if (affected.size() >= 4) return "Platform-wide elevated alerts across " + affected.size() + " services";
        if (affected.contains("settlement"))  return "Settlement layer degradation";
        if (affected.contains("aml-compliance")) return "AML screening service elevated alerts";
        if (affected.contains("fraud-scoring")) return "Fraud scoring service elevated alerts";
        if (affected.contains("routing-execution")) return "Rail routing failures — possible connectivity issue";
        if (affected.size() == 1) return "Isolated elevated alerts in " + affected.get(0);
        return "Multiple services with elevated alerts: " + String.join(", ", affected);
    }

    private String deriveSeverity(int affectedCount,
                                  Map<String, Long> alerts,
                                  Map<String, Long> errors) {
        long maxAlerts = alerts.values().stream().mapToLong(Long::longValue).max().orElse(0);
        long maxErrors = errors.values().stream().mapToLong(Long::longValue).max().orElse(0);
        if (affectedCount >= 4 || maxAlerts >= 50) return "CRITICAL";
        if (affectedCount >= 2 || maxAlerts >= 20) return "HIGH";
        if (affectedCount >= 1 || maxErrors >= ERROR_LOG_THRESHOLD) return "MEDIUM";
        return "LOW";
    }

    private String suggestedAction(List<String> affected, boolean isSystemic) {
        if (!isSystemic) return "No action required — system operating within normal thresholds";
        if (affected.contains("settlement")) return "Check settlement service health and nostro account balances";
        if (affected.contains("aml-compliance")) return "Check AML screening provider connectivity and SDN list freshness";
        if (affected.contains("routing-execution")) return "Check rail connectivity — contact SWIFT/SEPA network operations";
        if (affected.size() >= 3) return "Escalate to on-call SRE — possible platform-wide incident";
        return "Investigate " + (affected.isEmpty() ? "elevated error logs" : affected.get(0)) + " service logs";
    }

    private String extractNarrative(String raw) {
        if (raw == null || raw.isBlank()) return null;
        String trimmed = raw.trim();
        if (trimmed.startsWith("```")) {
            int nl = trimmed.indexOf('\n');
            int last = trimmed.lastIndexOf("```");
            if (nl > 0 && last > nl) trimmed = trimmed.substring(nl + 1, last).trim();
        }
        int start = trimmed.indexOf('{');
        int end = trimmed.lastIndexOf('}');
        if (start < 0 || end <= start) return trimmed; // return as-is if not JSON
        try {
            JsonNode node = objectMapper.readTree(trimmed.substring(start, end + 1));
            JsonNode pattern = node.path("pattern");
            return pattern.isMissingNode() ? null : pattern.asText();
        } catch (Exception e) {
            return null;
        }
    }
}
