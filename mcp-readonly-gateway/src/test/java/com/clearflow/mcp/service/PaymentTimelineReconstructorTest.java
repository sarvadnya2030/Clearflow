package com.clearflow.mcp.service;

import com.clearflow.mcp.service.ElasticsearchLogFetcher.LogEntry;
import com.clearflow.mcp.service.PaymentTimelineReconstructor.PaymentTimeline;
import com.clearflow.mcp.service.PaymentTimelineReconstructor.StageStatus;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class PaymentTimelineReconstructorTest {

    private PaymentTimelineReconstructor reconstructor;

    @BeforeEach
    void setUp() {
        reconstructor = new PaymentTimelineReconstructor();
    }

    @Test
    void emptyLogs_returnsNotFoundTimeline() {
        PaymentTimeline timeline = reconstructor.reconstruct("PAY-001", List.of());

        assertThat(timeline.overallStatus()).isEqualTo("NOT_FOUND");
        assertThat(timeline.stages()).isEmpty();
        assertThat(timeline.failureStage()).isNull();
        assertThat(timeline.totalLogEvents()).isEqualTo(0);
    }

    @Test
    void settledPayment_allStagesCompleted() {
        List<LogEntry> logs = List.of(
                log("gateway",              "PAYMENT_SUBMITTED",    null, null, null, null),
                log("validation-enrichment","PAYMENT_VALIDATED",    null, null, null, null),
                log("fraud-scoring",        "FRAUD_SCORE_COMPUTED", null, null, null, null),
                log("aml-compliance",       "AML_SCREENING_COMPLETE", null, null, "CLEAR", null),
                log("routing-execution",    "PAYMENT_ROUTED",       null, null, null, null),
                log("settlement",           "SETTLEMENT_COMPLETE",  null, null, null, null),
                log("audit",               "AUDIT_CHAIN_APPENDED", null, null, null, null)
        );

        PaymentTimeline timeline = reconstructor.reconstruct("PAY-SETTLED", logs);

        assertThat(timeline.overallStatus()).isEqualTo("SETTLED");
        assertThat(timeline.failureStage()).isNull();
        assertThat(timeline.stages()).hasSize(7);
        assertThat(timeline.stages()).allMatch(s -> s.status() == StageStatus.COMPLETED);
    }

    @Test
    void amlSanctionsHit_failsAtAmlStageAndSkipsDownstream() {
        List<LogEntry> logs = List.of(
                log("gateway",              "PAYMENT_SUBMITTED",    null,  null,     null,  null),
                log("validation-enrichment","PAYMENT_VALIDATED",    null,  null,     null,  null),
                log("fraud-scoring",        "FRAUD_SCORE_COMPUTED", 0.25,  "LOW",    null,  null),
                log("aml-compliance",       "AML_SANCTIONS_HIT",   null,  null,     "HIT", "GAZPROMBANK")
        );

        PaymentTimeline timeline = reconstructor.reconstruct("PAY-AML", logs);

        assertThat(timeline.overallStatus()).isEqualTo("BLOCKED");
        assertThat(timeline.failureStage()).isNotNull();
        assertThat(timeline.failureStage().serviceId()).isEqualTo("aml-compliance");

        // Stages after failure should be SKIPPED
        assertThat(stageStatus(timeline, "routing-execution")).isEqualTo(StageStatus.SKIPPED);
        assertThat(stageStatus(timeline, "settlement")).isEqualTo(StageStatus.SKIPPED);
    }

    @Test
    void criticalFraudScore_failsAtFraudStage() {
        List<LogEntry> logs = List.of(
                log("gateway",       "PAYMENT_SUBMITTED",    null, null, null, null),
                log("fraud-scoring", "FRAUD_SCORE_COMPUTED", 0.97, "CRITICAL", null, null)
        );

        PaymentTimeline timeline = reconstructor.reconstruct("PAY-FRAUD", logs);

        assertThat(timeline.overallStatus()).isEqualTo("BLOCKED");
        assertThat(timeline.failureStage()).isNotNull();
        assertThat(timeline.failureStage().serviceId()).isEqualTo("fraud-scoring");
    }

    @Test
    void noLogsFromService_pendingBeforeFailure_skippedAfter() {
        // Only gateway + AML hit — validation has no logs (PENDING), routing/settlement skipped
        List<LogEntry> logs = List.of(
                log("gateway",      "PAYMENT_SUBMITTED", null, null, null, null),
                log("aml-compliance","AML_SANCTIONS_HIT", null, null, "HIT", "ENTITY_A")
        );

        PaymentTimeline timeline = reconstructor.reconstruct("PAY-SKIP", logs);

        assertThat(stageStatus(timeline, "validation-enrichment")).isEqualTo(StageStatus.PENDING);
        assertThat(stageStatus(timeline, "routing-execution")).isEqualTo(StageStatus.SKIPPED);
        assertThat(stageStatus(timeline, "settlement")).isEqualTo(StageStatus.SKIPPED);
    }

    @Test
    void totalLogEventsAndTimestampsAreRecorded() {
        List<LogEntry> logs = List.of(
                logWithTs("gateway", "PAYMENT_SUBMITTED", "2024-01-01T10:00:00Z"),
                logWithTs("settlement", "SETTLEMENT_COMPLETE", "2024-01-01T10:00:01Z")
        );

        PaymentTimeline timeline = reconstructor.reconstruct("PAY-TS", logs);

        assertThat(timeline.totalLogEvents()).isEqualTo(2);
        assertThat(timeline.firstEventTimestamp()).isEqualTo("2024-01-01T10:00:00Z");
        assertThat(timeline.lastEventTimestamp()).isEqualTo("2024-01-01T10:00:01Z");
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private StageStatus stageStatus(PaymentTimeline timeline, String serviceId) {
        return timeline.stages().stream()
                .filter(s -> serviceId.equals(s.serviceId()))
                .findFirst()
                .orElseThrow(() -> new AssertionError("Stage not found: " + serviceId))
                .status();
    }

    private LogEntry log(String service, String eventType, Double fraudScore, String riskBand,
                         String screeningResult, String listHit) {
        return new LogEntry(
                "2024-01-01T10:00:00Z", service, "INFO", "test message",
                "PAY-TEST", null, null,
                eventType, null,
                fraudScore, riskBand,
                screeningResult, null, listHit,
                null, null,
                null, null, null, null
        );
    }

    private LogEntry logWithTs(String service, String eventType, String timestamp) {
        return new LogEntry(
                timestamp, service, "INFO", "test message",
                "PAY-TS", null, null,
                eventType, null,
                null, null,
                null, null, null,
                null, null,
                null, null, null, null
        );
    }
}
