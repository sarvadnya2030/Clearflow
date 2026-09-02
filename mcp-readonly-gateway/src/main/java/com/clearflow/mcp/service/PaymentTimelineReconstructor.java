package com.clearflow.mcp.service;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.stereotype.Service;

import com.clearflow.mcp.service.ElasticsearchLogFetcher.LogEntry;

/**
 * Reconstructs a human-readable payment pipeline timeline from raw ES log entries.
 *
 * Problem it solves: a payment generates 40-80 log entries across 7 services.
 * Without structure, these are just noise. This class answers two questions:
 *   1. Which pipeline stage did the payment fail at?
 *   2. What happened at each stage before that?
 *
 * Output:
 *   Stage 1 — GATEWAY:       ✅ SUBMITTED    14:23:01  (12ms)
 *   Stage 2 — VALIDATION:    ✅ VALIDATED    14:23:01  (88ms)
 *   Stage 3 — FRAUD:         ✅ LOW_RISK     14:23:01  (152ms)
 *   Stage 4 — AML:           ❌ BLOCKED      14:23:02  ← FAILURE HERE
 *   Stage 5 — ROUTING:       ⏭  SKIPPED
 *   Stage 6 — SETTLEMENT:    ⏭  SKIPPED
 *   Stage 7 — AUDIT:         ✅ LOGGED       14:23:02
 */
@Service
public class PaymentTimelineReconstructor {

    // ── Domain model ──────────────────────────────────────────────────────────

    public enum StageStatus { COMPLETED, FAILED, SKIPPED, PENDING }

    public record PipelineStage(
            int order,
            String serviceId,       // "aml-compliance"
            String displayName,     // "AML Compliance"
            StageStatus status,
            String keyEvent,        // e.g. "AML_SANCTIONS_HIT"
            String keyDetail,       // e.g. "matchScore=0.92, entity=GAZPROMBANK"
            String timestamp,       // @timestamp of the key event
            Long durationMs,
            List<LogEntry> logs     // all log entries from this stage
    ) {}

    public record PaymentTimeline(
            String paymentId,
            String overallStatus,           // SETTLED | BLOCKED | FAILED | IN_PROGRESS
            List<PipelineStage> stages,
            PipelineStage failureStage,     // null if payment succeeded
            String failureService,
            String firstEventTimestamp,
            String lastEventTimestamp,
            int totalLogEvents
    ) {}

    // ── Pipeline stage definitions (in processing order) ─────────────────────

    private record StageDefinition(
            int order,
            String serviceId,
            String displayName,
            Set<String> successEvents,
            Set<String> failureEvents
    ) {}

    private static final List<StageDefinition> PIPELINE_STAGES = List.of(
            new StageDefinition(1, "gateway", "Payment Gateway",
                    Set.of("PAYMENT_SUBMITTED", "PAYMENT_INITIATED"),
                    Set.of("PAYMENT_REJECTED")),
            new StageDefinition(2, "validation-enrichment", "Validation & Enrichment",
                    Set.of("IBAN_VALIDATED", "EMBARGO_CHECK", "PAYMENT_VALIDATED"),
                    Set.of("PAYMENT_REJECTED", "VALIDATION_FAILED", "EMBARGO_HIT")),
            new StageDefinition(3, "fraud-scoring", "Fraud Scoring",
                    Set.of("FRAUD_SCORE_COMPUTED"),
                    Set.of("PAYMENT_BLOCKED")),
            new StageDefinition(4, "aml-compliance", "AML Compliance",
                    Set.of("AML_SCREENING_COMPLETE"),
                    Set.of("AML_SANCTIONS_HIT", "PAYMENT_BLOCKED")),
            new StageDefinition(5, "routing-execution", "Rail Routing",
                    Set.of("RAIL_SELECTED", "PAYMENT_ROUTED"),
                    Set.of("ROUTING_FAILED", "PAYMENT_FAILED")),
            new StageDefinition(6, "settlement", "Settlement",
                    Set.of("SETTLEMENT_COMPLETE"),
                    Set.of("SETTLEMENT_FAILED", "ACCOUNTING_IMBALANCE")),
            new StageDefinition(7, "audit", "Audit Chain",
                    Set.of("AUDIT_CHAIN_APPENDED"),
                    Set.of())
    );

    // Events that always indicate a blocked/failed payment regardless of service
    private static final Set<String> GLOBAL_FAILURE_EVENTS = Set.of(
            "AML_SANCTIONS_HIT", "PAYMENT_BLOCKED", "PAYMENT_FAILED",
            "PAYMENT_REJECTED", "ROUTING_FAILED", "SETTLEMENT_FAILED"
    );

    // ── Main reconstruction logic ─────────────────────────────────────────────

    public PaymentTimeline reconstruct(String paymentId, List<LogEntry> rawLogs) {
        if (rawLogs.isEmpty()) {
            return emptyTimeline(paymentId);
        }

        // Group log entries by service
        Map<String, List<LogEntry>> byService = rawLogs.stream()
                .filter(e -> e.service() != null)
                .collect(Collectors.groupingBy(LogEntry::service));

        // Build each stage
        List<PipelineStage> stages = new ArrayList<>();
        PipelineStage failureStage = null;
        boolean failureFound = false;

        for (StageDefinition def : PIPELINE_STAGES) {
            List<LogEntry> stageLogs = byService.getOrDefault(def.serviceId(), List.of());

            StageStatus status;
            String keyEvent = null;
            String keyDetail = null;
            String timestamp = null;
            Long durationMs = null;

            if (stageLogs.isEmpty()) {
                // No logs from this stage
                status = failureFound ? StageStatus.SKIPPED : StageStatus.PENDING;
            } else {
                // Find the key event (failure first, then success, then latest)
                LogEntry failureLog = stageLogs.stream()
                        .filter(e -> isFailureEvent(e, def))
                        .findFirst()
                        .orElse(null);

                if (failureLog != null) {
                    status = StageStatus.FAILED;
                    keyEvent = failureLog.eventType();
                    keyDetail = buildKeyDetail(failureLog);
                    timestamp = failureLog.timestamp();
                    durationMs = failureLog.durationMs();
                    failureFound = true;
                } else {
                    // Check for success events
                    LogEntry successLog = stageLogs.stream()
                            .filter(e -> e.eventType() != null && def.successEvents().contains(e.eventType()))
                            .reduce((first, second) -> second) // take last success event
                            .orElse(stageLogs.get(stageLogs.size() - 1));

                    status = StageStatus.COMPLETED;
                    keyEvent = successLog.eventType() != null ? successLog.eventType() : "PROCESSED";
                    keyDetail = buildKeyDetail(successLog);
                    timestamp = successLog.timestamp();
                    durationMs = successLog.durationMs();
                }
            }

            PipelineStage stage = new PipelineStage(
                    def.order(), def.serviceId(), def.displayName(),
                    status, keyEvent, keyDetail, timestamp, durationMs,
                    stageLogs
            );
            stages.add(stage);

            if (status == StageStatus.FAILED && failureStage == null) {
                failureStage = stage;
            }
        }

        // Determine overall status
        String overallStatus = determineOverallStatus(stages, rawLogs);

        // Timestamps
        String first = rawLogs.stream()
                .filter(e -> e.timestamp() != null)
                .min(Comparator.comparing(LogEntry::timestamp))
                .map(LogEntry::timestamp).orElse(null);
        String last = rawLogs.stream()
                .filter(e -> e.timestamp() != null)
                .max(Comparator.comparing(LogEntry::timestamp))
                .map(LogEntry::timestamp).orElse(null);

        return new PaymentTimeline(
                paymentId, overallStatus, stages, failureStage,
                failureStage != null ? failureStage.serviceId() : null,
                first, last, rawLogs.size()
        );
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private boolean isFailureEvent(LogEntry entry, StageDefinition def) {
        if (entry.eventType() != null && def.failureEvents().contains(entry.eventType())) return true;
        if (entry.eventType() != null && GLOBAL_FAILURE_EVENTS.contains(entry.eventType())) return true;
        if ("ERROR".equals(entry.level())) return true;
        // Fraud: CRITICAL riskBand means it was blocked
        if ("fraud-scoring".equals(def.serviceId())
                && entry.riskBand() != null
                && entry.riskBand().equals("CRITICAL")) return true;
        // AML: HIT means blocked
        if ("aml-compliance".equals(def.serviceId())
                && "HIT".equals(entry.screeningResult())) return true;
        return false;
    }

    /**
     * Build a concise detail string from the most relevant fields of a log entry.
     * This becomes the "keyDetail" shown in the timeline and evidence list.
     */
    private String buildKeyDetail(LogEntry e) {
        List<String> parts = new ArrayList<>();

        if (e.eventType() != null)       parts.add("event=" + e.eventType());
        if (e.fraudScore() != null)      parts.add("fraudScore=" + String.format("%.2f", e.fraudScore()));
        if (e.riskBand() != null)        parts.add("riskBand=" + e.riskBand());
        if (e.screeningResult() != null) parts.add("result=" + e.screeningResult());
        if (e.matchScore() != null)      parts.add("matchScore=" + String.format("%.2f", e.matchScore()));
        if (e.listHit() != null && !e.listHit().isBlank()) parts.add("entity=" + e.listHit());
        if (e.rail() != null)            parts.add("rail=" + e.rail());
        if (e.currency() != null)        parts.add("currency=" + e.currency());
        if (e.debtorCountry() != null && e.creditorCountry() != null)
            parts.add("corridor=" + e.debtorCountry() + "→" + e.creditorCountry());
        if (e.durationMs() != null)      parts.add("durationMs=" + e.durationMs());

        // Fallback: first 120 chars of message
        if (parts.isEmpty() && e.message() != null) {
            parts.add(e.message().length() > 120 ? e.message().substring(0, 120) : e.message());
        }

        return String.join(", ", parts);
    }

    private String determineOverallStatus(List<PipelineStage> stages, List<LogEntry> logs) {
        // Check if any log has a final terminal event
        boolean hasSettled = logs.stream()
                .anyMatch(e -> "SETTLEMENT_COMPLETE".equals(e.eventType()));
        boolean hasBlocked = logs.stream()
                .anyMatch(e -> e.eventType() != null && GLOBAL_FAILURE_EVENTS.contains(e.eventType()));
        boolean hasFailed = stages.stream()
                .anyMatch(s -> s.status() == StageStatus.FAILED);

        if (hasSettled) return "SETTLED";
        if (hasBlocked || hasFailed) return "BLOCKED";
        // Check if payment is still flowing
        boolean hasAudit = stages.stream()
                .filter(s -> "audit".equals(s.serviceId()))
                .anyMatch(s -> s.status() == StageStatus.COMPLETED);
        if (hasAudit) return "SETTLED";
        return "IN_PROGRESS";
    }

    private PaymentTimeline emptyTimeline(String paymentId) {
        return new PaymentTimeline(
                paymentId, "NOT_FOUND",
                List.of(), null, null, null, null, 0
        );
    }
}
