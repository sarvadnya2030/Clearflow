package com.clearflow.mcp.service;

import com.clearflow.mcp.service.PaymentTimelineReconstructor.PaymentTimeline;
import com.clearflow.mcp.service.PaymentTimelineReconstructor.PipelineStage;
import com.clearflow.mcp.service.PaymentTimelineReconstructor.StageStatus;
import com.clearflow.mcp.service.RootCauseClassifier.ClassificationResult;

/**
 * Engineered prompts for the root cause analysis LLM call.
 *
 * Design constraints for small models (qwen3.5:0.8b / llama-3.1-8b):
 * - System prompt ≤ 300 tokens
 * - User prompt ≤ 600 tokens
 * - Explicit JSON schema — no chain-of-thought, output is directly parsed
 * - One concrete example in system prompt anchors the format
 */
public final class PromptTemplates {

    private PromptTemplates() {}

    // ── Root cause explanation prompt ─────────────────────────────────────────

    public static String rootCauseSystem() {
        return """
                You are a payment operations AI for a bank. Given a structured payment failure report, \
                write a concise root cause explanation for a compliance officer.

                Rules:
                - Reply ONLY with valid JSON, no markdown, no preamble
                - Keep narrative under 80 words
                - Use plain English, no jargon acronyms without expansion
                - Follow this exact schema:

                {
                  "summary": "<1-2 sentence plain-English root cause>",
                  "immediateAction": "<one specific action the operator should take now>",
                  "regulatoryNote": "<relevant regulation or policy reference, or null>",
                  "confidence": "HIGH|MEDIUM|LOW"
                }
                """;
    }

    public static String rootCauseUser(PaymentTimeline timeline, ClassificationResult classification) {
        StringBuilder sb = new StringBuilder();
        sb.append("PAYMENT FAILURE REPORT\n");
        sb.append("paymentId: ").append(timeline.paymentId()).append("\n");
        sb.append("overallStatus: ").append(timeline.overallStatus()).append("\n");
        sb.append("failedAt: ").append(
                classification.failureStage() != null ? classification.failureStage() : "unknown").append("\n");
        sb.append("causeCategory: ").append(classification.category()).append("\n");
        sb.append("primaryCause: ").append(classification.primaryCause()).append("\n");
        if (classification.primaryEvidence() != null) {
            sb.append("evidence: ").append(classification.primaryEvidence()).append("\n");
        }
        sb.append("classifierConfidence: ").append(classification.confidence()).append("\n\n");

        sb.append("PIPELINE STAGES:\n");
        for (PipelineStage stage : timeline.stages()) {
            String icon = stageIcon(stage.status());
            sb.append(String.format("  Stage %d — %-25s %s %s",
                    stage.order(), stage.displayName() + ":", icon,
                    stage.status().name()));
            if (stage.keyEvent() != null) sb.append(" [").append(stage.keyEvent()).append("]");
            sb.append("\n");
        }

        sb.append("\ntotalLogEvents: ").append(timeline.totalLogEvents()).append("\n");
        sb.append("timespan: ").append(timeline.firstEventTimestamp())
          .append(" → ").append(timeline.lastEventTimestamp()).append("\n");

        return sb.toString();
    }

    // ── Systemic failure prompt ────────────────────────────────────────────────

    public static String systemicSystem() {
        return """
                You are a payment operations AI. Given aggregated error counts across services, \
                identify if there is a systemic (infrastructure or widespread) failure pattern.

                Reply ONLY with valid JSON:
                {
                  "isSystemic": true|false,
                  "affectedServices": ["service1", "service2"],
                  "pattern": "<short description of the pattern>",
                  "severity": "CRITICAL|HIGH|MEDIUM|LOW",
                  "suggestedAction": "<immediate triage step>"
                }
                """;
    }

    public static String systemicUser(java.util.Map<String, Long> alertsByService,
                                      java.util.Map<String, Long> errorsByService,
                                      int windowMinutes) {
        StringBuilder sb = new StringBuilder();
        sb.append("SYSTEMIC ALERT REPORT — last ").append(windowMinutes).append(" minutes\n\n");

        sb.append("HIGH alerts by service:\n");
        if (alertsByService.isEmpty()) {
            sb.append("  (none)\n");
        } else {
            alertsByService.forEach((svc, count) ->
                    sb.append("  ").append(svc).append(": ").append(count).append(" alerts\n"));
        }

        sb.append("\nERROR-level logs by service:\n");
        if (errorsByService.isEmpty()) {
            sb.append("  (none)\n");
        } else {
            errorsByService.forEach((svc, count) ->
                    sb.append("  ").append(svc).append(": ").append(count).append(" errors\n"));
        }

        return sb.toString();
    }

    // ── Incident-with-code-context prompt ─────────────────────────────────────

    public static String incidentWithCodeSystem() {
        return """
                You are a senior payments platform engineer at a bank. Given a payment incident \
                report AND the relevant source code context from the codebase, explain exactly \
                what failed and how an engineer should fix it.

                Rules:
                - Reply ONLY with valid JSON, no markdown, no preamble
                - Reference specific Java class names and methods from the code context
                - Keep each field concise (under 50 words each)
                - Follow this exact schema:

                {
                  "failedClass": "<Java class name that owns the failure>",
                  "failedMethod": "<method name where the failure occurred>",
                  "sourceFile": "<relative path to the Java source file>",
                  "rootCause": "<1-2 sentence root cause>",
                  "fixSteps": ["<step 1>", "<step 2>", "<step 3>"],
                  "regulatoryRisk": "<compliance impact or null>",
                  "confidence": "HIGH|MEDIUM|LOW"
                }
                """;
    }

    public static String incidentWithCodeUser(PaymentTimeline timeline,
                                              ClassificationResult classification,
                                              String codeContext) {
        StringBuilder sb = new StringBuilder();
        sb.append("PAYMENT INCIDENT REPORT\n");
        sb.append("paymentId:    ").append(timeline.paymentId()).append("\n");
        sb.append("overallStatus:").append(timeline.overallStatus()).append("\n");
        sb.append("failedAt:     ").append(
                classification.failureStage() != null ? classification.failureStage() : "unknown").append("\n");
        sb.append("causeCategory:").append(classification.category()).append("\n");
        sb.append("primaryCause: ").append(classification.primaryCause()).append("\n");
        if (classification.primaryEvidence() != null) {
            sb.append("evidence:     ").append(classification.primaryEvidence()).append("\n");
        }
        sb.append("confidence:   ").append(classification.confidence()).append("\n\n");

        sb.append("PIPELINE STAGES:\n");
        for (PipelineStage stage : timeline.stages()) {
            if (stage.status() == StageStatus.FAILED || stage.status() == StageStatus.COMPLETED) {
                String icon = stageIcon(stage.status());
                sb.append(String.format("  Stage %d %-22s %s %s",
                        stage.order(), stage.displayName() + ":", icon, stage.status().name()));
                if (stage.keyEvent() != null) sb.append(" [").append(stage.keyEvent()).append("]");
                sb.append("\n");
                if (stage.keyDetail() != null && stage.status() == StageStatus.FAILED) {
                    sb.append("    Evidence: ").append(stage.keyDetail()).append("\n");
                }
            }
        }

        sb.append("\n").append(codeContext);
        return sb.toString();
    }

    // ── Broker cascade prompt ─────────────────────────────────────────────────

    public static String brokerCascadeSystem() {
        return """
                You are a senior distributed-systems engineer at a bank. Given a payment cascade \
                failure report with broker topology context, explain how the failure propagated \
                across service boundaries via Kafka/ActiveMQ/Solace, and give precise fix steps.

                Rules:
                - Reply ONLY with valid JSON, no markdown, no preamble
                - Reference exact class names, topic/queue names, and source file paths from the context
                - Under 60 words per text field
                - Schema:

                {
                  "propagationPath": ["<hop 1: service → broker → service>", "<hop 2>", "..."],
                  "rootService": "<service where cascade originated>",
                  "rootClass": "<Java class that failed first>",
                  "brokerBottleneck": "<topic/queue name that backed up>",
                  "fixSteps": ["<step 1>", "<step 2>", "<step 3>"],
                  "preventionConfig": "<config change to prevent recurrence>",
                  "severity": "CRITICAL|HIGH|MEDIUM"
                }
                """;
    }

    public static String brokerCascadeUser(String paymentId, String cascadeType,
                                            String cascadeEventSummary,
                                            String brokerContext,
                                            String pipelineTopology) {
        StringBuilder sb = new StringBuilder();
        sb.append("CASCADE FAILURE REPORT\n");
        sb.append("paymentId:   ").append(paymentId).append("\n");
        sb.append("cascadeType: ").append(cascadeType).append("\n\n");

        sb.append("CASCADE EVENT TIMELINE:\n");
        sb.append(cascadeEventSummary).append("\n");

        sb.append("BROKER TOPOLOGY AT FAILURE POINT:\n");
        sb.append(brokerContext).append("\n");

        sb.append("FULL PIPELINE:\n");
        // Keep pipeline compact — first 15 lines only
        String[] lines = pipelineTopology.split("\n");
        int shown = 0;
        for (String line : lines) {
            if (shown++ > 15) break;
            sb.append(line).append("\n");
        }

        return sb.toString();
    }

    // ── Helper ────────────────────────────────────────────────────────────────

    private static String stageIcon(StageStatus status) {
        return switch (status) {
            case COMPLETED -> "✅";
            case FAILED    -> "❌";
            case SKIPPED   -> "⏭ ";
            case PENDING   -> "⏳";
        };
    }
}
