package com.clearflow.mcp.service;

import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import com.clearflow.mcp.llm.LLMClient;
import com.clearflow.mcp.llm.LLMMessage;
import com.clearflow.mcp.service.ElasticsearchLogFetcher.LogEntry;
import com.clearflow.mcp.service.PaymentTimelineReconstructor.PaymentTimeline;
import com.clearflow.mcp.service.RootCauseClassifier.ClassificationResult;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * Orchestrates the full root cause analysis pipeline for a single payment failure.
 *
 * Pipeline:
 *   1. Fetch all log entries for the paymentId from ES (ElasticsearchLogFetcher)
 *   2. Reconstruct 7-stage pipeline timeline (PaymentTimelineReconstructor)
 *   3. Apply rule-based classification (RootCauseClassifier)
 *   4. Generate human narrative via LLM (LLMClient)
 *   5. Return structured ExplainResponse — always includes structured data even if LLM fails
 *
 * Resilience: LLM failure is non-fatal. The response always includes the deterministic
 * classification so operators get actionable information even if the narrative is missing.
 */
@Service
public class RootCauseAnalysisService {

    private static final Logger log = LoggerFactory.getLogger(RootCauseAnalysisService.class);

    // ── Response type ─────────────────────────────────────────────────────────

    public record ExplainResponse(
            String paymentId,
            String overallStatus,
            // Rule-based classification (always present)
            String causeCategory,
            String primaryCause,
            String primaryEvidence,
            String classifierConfidence,
            String failedAtService,
            String failedAtStage,
            // LLM narrative (may be null if LLM unavailable)
            String narrativeSummary,
            String immediateAction,
            String regulatoryNote,
            String narrativeConfidence,
            String llmProvider,
            // Full timeline
            PaymentTimeline timeline,
            // Metadata
            long analysisMs
    ) {}

    // ── Dependencies ──────────────────────────────────────────────────────────

    private final ElasticsearchLogFetcher logFetcher;
    private final PaymentTimelineReconstructor reconstructor;
    private final RootCauseClassifier classifier;
    private final LLMClient llmClient;
    private final ObjectMapper objectMapper;

    public RootCauseAnalysisService(ElasticsearchLogFetcher logFetcher,
                                    PaymentTimelineReconstructor reconstructor,
                                    RootCauseClassifier classifier,
                                    LLMClient llmClient,
                                    ObjectMapper objectMapper) {
        this.logFetcher = logFetcher;
        this.reconstructor = reconstructor;
        this.classifier = classifier;
        this.llmClient = llmClient;
        this.objectMapper = objectMapper;
    }

    // ── Main entry point ──────────────────────────────────────────────────────

    public ExplainResponse explain(String paymentId) {
        long start = System.currentTimeMillis();

        // Step 1: Fetch logs
        List<LogEntry> logs = logFetcher.fetchLogsForPayment(paymentId);

        // Step 2: Reconstruct timeline
        PaymentTimeline timeline = reconstructor.reconstruct(paymentId, logs);

        // If the payment does not exist yet in the log pipeline, return a safe stub
        if ("NOT_FOUND".equals(timeline.overallStatus())) {
            long elapsed = System.currentTimeMillis() - start;
            return new ExplainResponse(
                    paymentId,
                    "NOT_FOUND",
                    "NO_DATA",
                    "No logs found for this payment ID",
                    "No Elasticsearch log entries for paymentId",
                    "LOW",
                    null,
                    null,
                    "No payment events found in Elasticsearch. Ensure ingestion and Kafka are running, then retry.",
                    "Check the payment ingest generator and pipeline health, then resubmit.",
                    "N/A",
                    "0.0",
                    "none",
                    timeline,
                    elapsed
            );
        }

        // Step 3: Rule-based classification
        ClassificationResult classification = classifier.classify(timeline);

        // Step 4: LLM narrative
        String summary = null, immediateAction = null, regulatoryNote = null, llmConfidence = null;
        String llmProvider = llmClient.providerName();

        if (!"NOT_FOUND".equals(timeline.overallStatus())) {
            try {
                String sysPrompt = PromptTemplates.rootCauseSystem();
                String userPrompt = PromptTemplates.rootCauseUser(timeline, classification);
                String raw = llmClient.chat(List.of(
                        new LLMMessage("system", sysPrompt),
                        new LLMMessage("user", userPrompt)
                ));
                JsonNode json = parseJson(raw);
                if (json != null) {
                    summary = text(json, "summary");
                    immediateAction = text(json, "immediateAction");
                    regulatoryNote = text(json, "regulatoryNote");
                    llmConfidence = text(json, "confidence");
                }
            } catch (Exception e) {
                log.warn("LLM narrative generation failed for {} — returning structured data only: {}",
                        paymentId, e.getMessage());
            }
        }

        long elapsed = System.currentTimeMillis() - start;
        log.info("Root cause analysis complete for {} in {}ms — category={} confidence={}",
                paymentId, elapsed, classification.category(), classification.confidence());

        return new ExplainResponse(
                paymentId,
                timeline.overallStatus(),
                classification.category().name(),
                classification.primaryCause(),
                classification.primaryEvidence(),
                classification.confidence().name(),
                classification.failureService(),
                classification.failureStage(),
                summary,
                immediateAction,
                regulatoryNote,
                llmConfidence,
                llmProvider,
                timeline,
                elapsed
        );
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    /**
     * Extract JSON from LLM output. LLMs sometimes wrap JSON in markdown fences.
     */
    private JsonNode parseJson(String raw) {
        if (raw == null || raw.isBlank()) return null;
        String trimmed = raw.trim();

        // Strip common markdown fences: ```json ... ``` or ``` ... ```
        if (trimmed.startsWith("```")) {
            int firstNewline = trimmed.indexOf('\n');
            int lastFence = trimmed.lastIndexOf("```");
            if (firstNewline > 0 && lastFence > firstNewline) {
                trimmed = trimmed.substring(firstNewline + 1, lastFence).trim();
            }
        }

        // Find the outermost JSON object
        int start = trimmed.indexOf('{');
        int end = trimmed.lastIndexOf('}');
        if (start < 0 || end <= start) return null;
        trimmed = trimmed.substring(start, end + 1);

        try {
            return objectMapper.readTree(trimmed);
        } catch (Exception e) {
            log.debug("Failed to parse LLM JSON response: {}", e.getMessage());
            return null;
        }
    }

    private String text(JsonNode node, String field) {
        if (node == null) return null;
        JsonNode v = node.path(field);
        return v.isMissingNode() || v.isNull() ? null : v.asText();
    }
}
