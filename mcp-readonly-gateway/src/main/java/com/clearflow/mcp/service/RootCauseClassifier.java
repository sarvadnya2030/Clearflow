package com.clearflow.mcp.service;

import com.clearflow.mcp.service.ElasticsearchLogFetcher.LogEntry;
import com.clearflow.mcp.service.PaymentTimelineReconstructor.PaymentTimeline;
import com.clearflow.mcp.service.PaymentTimelineReconstructor.PipelineStage;
import com.clearflow.mcp.service.PaymentTimelineReconstructor.StageStatus;
import org.springframework.stereotype.Service;

import java.util.List;

/**
 * Rule-based root cause classifier for payment failures.
 *
 * Design principle: deterministic before generative.
 * This classifier produces a structured, auditable result using a priority-ordered
 * rule table. The LLM (in RootCauseAnalysisService) only writes the human narrative
 * on top of this — it never drives the classification itself.
 *
 * Rule priority (first match wins):
 *   1. AML sanctions hit              → AML_SANCTIONS        (HIGH)
 *   2. Fraud score CRITICAL           → FRAUD_CRITICAL        (HIGH)
 *   3. Velocity breach (5+ payments)  → FRAUD_VELOCITY        (HIGH)
 *   4. Embargo hit                    → EMBARGO_BLOCKED       (HIGH)
 *   5. Duplicate payment              → DUPLICATE_PAYMENT     (HIGH)
 *   6. Validation failure             → VALIDATION_FAILURE    (MEDIUM)
 *   7. Routing failure                → ROUTING_FAILURE       (MEDIUM)
 *   8. Settlement failure             → SETTLEMENT_FAILURE    (MEDIUM)
 *   9. ERROR level in any service     → SYSTEM_ERROR          (MEDIUM)
 *  10. Default                        → UNKNOWN               (LOW)
 */
@Service
public class RootCauseClassifier {

    // ── Domain model ──────────────────────────────────────────────────────────

    public enum CauseCategory {
        AML_SANCTIONS,
        FRAUD_CRITICAL,
        FRAUD_VELOCITY,
        EMBARGO_BLOCKED,
        DUPLICATE_PAYMENT,
        VALIDATION_FAILURE,
        ROUTING_FAILURE,
        SETTLEMENT_FAILURE,
        SYSTEM_ERROR,
        UNKNOWN
    }

    public enum Confidence { HIGH, MEDIUM, LOW }

    public record ClassificationResult(
            CauseCategory category,
            String primaryCause,        // one-line human-readable cause
            String primaryEvidence,     // key log detail that triggered this rule
            Confidence confidence,
            String failureService,
            String failureStage
    ) {}

    // ── Classification entry point ────────────────────────────────────────────

    public ClassificationResult classify(PaymentTimeline timeline) {
        List<LogEntry> logs = timeline.stages().stream()
                .flatMap(s -> s.logs().stream())
                .toList();

        // Rule 1: AML sanctions hit
        ClassificationResult aml = checkAmlSanctions(timeline, logs);
        if (aml != null) return aml;

        // Rule 2: Fraud score CRITICAL
        ClassificationResult fraud = checkFraudCritical(timeline, logs);
        if (fraud != null) return fraud;

        // Rule 3: Velocity breach
        ClassificationResult velocity = checkVelocityBreach(logs);
        if (velocity != null) return velocity;

        // Rule 4: Embargo hit
        ClassificationResult embargo = checkEmbargo(timeline, logs);
        if (embargo != null) return embargo;

        // Rule 5: Duplicate payment
        ClassificationResult duplicate = checkDuplicate(logs);
        if (duplicate != null) return duplicate;

        // Rule 6: Validation failure
        ClassificationResult validation = checkValidationFailure(timeline);
        if (validation != null) return validation;

        // Rule 7: Routing failure
        ClassificationResult routing = checkRoutingFailure(timeline);
        if (routing != null) return routing;

        // Rule 8: Settlement failure
        ClassificationResult settlement = checkSettlementFailure(timeline);
        if (settlement != null) return settlement;

        // Rule 9: System error (ERROR log level in any service)
        ClassificationResult sysError = checkSystemError(timeline, logs);
        if (sysError != null) return sysError;

        // Rule 10: Default — no rule matched
        return new ClassificationResult(
                CauseCategory.UNKNOWN,
                "No specific failure cause identified",
                timeline.overallStatus(),
                Confidence.LOW,
                null, null
        );
    }

    // ── Rule implementations ──────────────────────────────────────────────────

    private ClassificationResult checkAmlSanctions(PaymentTimeline timeline, List<LogEntry> logs) {
        // Match on event type
        LogEntry hit = logs.stream()
                .filter(e -> "AML_SANCTIONS_HIT".equals(e.eventType()))
                .findFirst().orElse(null);

        // Also match on screeningResult=HIT
        if (hit == null) {
            hit = logs.stream()
                    .filter(e -> "HIT".equals(e.screeningResult()))
                    .findFirst().orElse(null);
        }

        if (hit == null) return null;

        String evidence = buildEvidence(hit);
        String cause = hit.listHit() != null
                ? "Payment blocked: AML sanctions hit — matched entity: " + hit.listHit()
                : "Payment blocked: AML sanctions screening returned HIT";

        return new ClassificationResult(
                CauseCategory.AML_SANCTIONS, cause, evidence,
                Confidence.HIGH, "aml-compliance", "AML Compliance"
        );
    }

    private ClassificationResult checkFraudCritical(PaymentTimeline timeline, List<LogEntry> logs) {
        LogEntry critical = logs.stream()
                .filter(e -> "CRITICAL".equals(e.riskBand()))
                .findFirst().orElse(null);

        if (critical == null) {
            // Also check: fraud stage FAILED with a high score
            PipelineStage fraudStage = stageById(timeline, "fraud-scoring");
            if (fraudStage == null || fraudStage.status() != StageStatus.FAILED) return null;
            critical = logs.stream()
                    .filter(e -> "fraud-scoring".equals(e.service()) && e.fraudScore() != null)
                    .max((a, b) -> Double.compare(a.fraudScore(), b.fraudScore()))
                    .orElse(null);
            if (critical == null) return null;
        }

        String score = critical.fraudScore() != null
                ? String.format("%.2f", critical.fraudScore()) : "n/a";
        String cause = "Payment blocked: fraud score " + score + " in CRITICAL risk band";
        String evidence = buildEvidence(critical);

        return new ClassificationResult(
                CauseCategory.FRAUD_CRITICAL, cause, evidence,
                Confidence.HIGH, "fraud-scoring", "Fraud Scoring"
        );
    }

    private ClassificationResult checkVelocityBreach(List<LogEntry> logs) {
        // Velocity breach is signalled by eventType=VELOCITY_BREACH or
        // by message containing "velocity" (case-insensitive)
        LogEntry velocity = logs.stream()
                .filter(e -> "VELOCITY_BREACH".equals(e.eventType())
                        || (e.message() != null
                            && e.message().toLowerCase().contains("velocity")))
                .findFirst().orElse(null);

        if (velocity == null) return null;

        String cause = "Payment blocked: velocity check triggered — rapid repeated payments from same account";
        return new ClassificationResult(
                CauseCategory.FRAUD_VELOCITY, cause, buildEvidence(velocity),
                Confidence.HIGH, velocity.service(), "Fraud Scoring"
        );
    }

    private ClassificationResult checkEmbargo(PaymentTimeline timeline, List<LogEntry> logs) {
        LogEntry embargo = logs.stream()
                .filter(e -> "EMBARGO_HIT".equals(e.eventType())
                        || "EMBARGO_CHECK".equals(e.eventType())
                        || (e.message() != null
                            && e.message().toLowerCase().contains("embargo")))
                .findFirst().orElse(null);

        if (embargo == null) {
            // Check validation stage failed with EMBARGO_HIT
            PipelineStage val = stageById(timeline, "validation-enrichment");
            if (val != null && val.status() == StageStatus.FAILED
                    && val.keyEvent() != null && val.keyEvent().contains("EMBARGO")) {
                embargo = val.logs().isEmpty() ? null : val.logs().get(0);
            }
        }

        if (embargo == null) return null;

        String cause = "Payment rejected: destination country under embargo restrictions";
        return new ClassificationResult(
                CauseCategory.EMBARGO_BLOCKED, cause, buildEvidence(embargo),
                Confidence.HIGH, "validation-enrichment", "Validation & Enrichment"
        );
    }

    private ClassificationResult checkDuplicate(List<LogEntry> logs) {
        LogEntry dup = logs.stream()
                .filter(e -> "DUPLICATE_PAYMENT".equals(e.eventType())
                        || (e.message() != null
                            && e.message().toLowerCase().contains("duplicate")))
                .findFirst().orElse(null);

        if (dup == null) return null;

        String cause = "Payment rejected: duplicate instruction ID — payment already processed";
        return new ClassificationResult(
                CauseCategory.DUPLICATE_PAYMENT, cause, buildEvidence(dup),
                Confidence.HIGH, dup.service(), "Payment Gateway"
        );
    }

    private ClassificationResult checkValidationFailure(PaymentTimeline timeline) {
        PipelineStage val = stageById(timeline, "validation-enrichment");
        if (val == null || val.status() != StageStatus.FAILED) return null;

        String cause = "Payment rejected: validation failed"
                + (val.keyDetail() != null ? " — " + val.keyDetail() : "");
        return new ClassificationResult(
                CauseCategory.VALIDATION_FAILURE, cause, val.keyDetail(),
                Confidence.MEDIUM, "validation-enrichment", "Validation & Enrichment"
        );
    }

    private ClassificationResult checkRoutingFailure(PaymentTimeline timeline) {
        PipelineStage routing = stageById(timeline, "routing-execution");
        if (routing == null || routing.status() != StageStatus.FAILED) return null;

        String cause = "Payment failed: rail routing could not find a viable execution path"
                + (routing.keyDetail() != null ? " — " + routing.keyDetail() : "");
        return new ClassificationResult(
                CauseCategory.ROUTING_FAILURE, cause, routing.keyDetail(),
                Confidence.MEDIUM, "routing-execution", "Rail Routing"
        );
    }

    private ClassificationResult checkSettlementFailure(PaymentTimeline timeline) {
        PipelineStage settlement = stageById(timeline, "settlement");
        if (settlement == null || settlement.status() != StageStatus.FAILED) return null;

        String cause = "Payment failed: settlement could not complete"
                + (settlement.keyDetail() != null ? " — " + settlement.keyDetail() : "");
        return new ClassificationResult(
                CauseCategory.SETTLEMENT_FAILURE, cause, settlement.keyDetail(),
                Confidence.MEDIUM, "settlement", "Settlement"
        );
    }

    private ClassificationResult checkSystemError(PaymentTimeline timeline, List<LogEntry> logs) {
        LogEntry error = logs.stream()
                .filter(e -> "ERROR".equals(e.level()))
                .findFirst().orElse(null);

        if (error == null) return null;

        String serviceName = error.service() != null ? error.service() : "unknown-service";
        String cause = "System error in " + serviceName
                + (error.message() != null
                   ? ": " + (error.message().length() > 100
                             ? error.message().substring(0, 100) + "..." : error.message())
                   : "");
        return new ClassificationResult(
                CauseCategory.SYSTEM_ERROR, cause, buildEvidence(error),
                Confidence.MEDIUM, serviceName, resolveStageDisplayName(timeline, serviceName)
        );
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private PipelineStage stageById(PaymentTimeline timeline, String serviceId) {
        return timeline.stages().stream()
                .filter(s -> serviceId.equals(s.serviceId()))
                .findFirst().orElse(null);
    }

    private String resolveStageDisplayName(PaymentTimeline timeline, String serviceId) {
        PipelineStage stage = stageById(timeline, serviceId);
        return stage != null ? stage.displayName() : serviceId;
    }

    /**
     * Builds a concise evidence string from the most diagnostic fields of a log entry.
     */
    private String buildEvidence(LogEntry e) {
        if (e == null) return null;
        StringBuilder sb = new StringBuilder();
        if (e.service() != null)         sb.append("service=").append(e.service());
        if (e.eventType() != null)       append(sb, "event=" + e.eventType());
        if (e.fraudScore() != null)      append(sb, "fraudScore=" + String.format("%.2f", e.fraudScore()));
        if (e.riskBand() != null)        append(sb, "riskBand=" + e.riskBand());
        if (e.screeningResult() != null) append(sb, "result=" + e.screeningResult());
        if (e.matchScore() != null)      append(sb, "matchScore=" + String.format("%.2f", e.matchScore()));
        if (e.listHit() != null && !e.listHit().isBlank()) append(sb, "entity=" + e.listHit());
        if (e.durationMs() != null)      append(sb, "durationMs=" + e.durationMs());
        if (sb.isEmpty() && e.message() != null) {
            String msg = e.message();
            sb.append(msg.length() > 120 ? msg.substring(0, 120) : msg);
        }
        return sb.toString();
    }

    private void append(StringBuilder sb, String part) {
        if (!sb.isEmpty()) sb.append(", ");
        sb.append(part);
    }
}
