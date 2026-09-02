package com.clearflow.mcp.service;

import com.clearflow.mcp.service.ElasticsearchLogFetcher.LogEntry;
import com.clearflow.mcp.service.PaymentTimelineReconstructor.PaymentTimeline;
import com.clearflow.mcp.service.RootCauseClassifier.CauseCategory;
import com.clearflow.mcp.service.RootCauseClassifier.ClassificationResult;
import com.clearflow.mcp.service.RootCauseClassifier.Confidence;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class RootCauseClassifierTest {

    private RootCauseClassifier classifier;
    private PaymentTimelineReconstructor reconstructor;

    @BeforeEach
    void setUp() {
        classifier = new RootCauseClassifier();
        reconstructor = new PaymentTimelineReconstructor();
    }

    @Test
    void amlSanctionsHit_classifiesAsAmlSanctions_highConfidence() {
        PaymentTimeline timeline = buildTimeline(List.of(
                log("gateway",       "PAYMENT_SUBMITTED",  null, null, null,  null),
                log("aml-compliance","AML_SANCTIONS_HIT",  null, null, "HIT", "GAZPROMBANK")
        ));

        ClassificationResult result = classifier.classify(timeline);

        assertThat(result.category()).isEqualTo(CauseCategory.AML_SANCTIONS);
        assertThat(result.confidence()).isEqualTo(Confidence.HIGH);
        assertThat(result.primaryEvidence()).contains("entity=GAZPROMBANK");
        assertThat(result.failureService()).isEqualTo("aml-compliance");
    }

    @Test
    void criticalRiskBand_classifiesAsFraudCritical_highConfidence() {
        PaymentTimeline timeline = buildTimeline(List.of(
                log("gateway",       "PAYMENT_SUBMITTED",    null, null, null, null),
                log("fraud-scoring", "FRAUD_SCORE_COMPUTED", 0.97, "CRITICAL", null, null)
        ));

        ClassificationResult result = classifier.classify(timeline);

        assertThat(result.category()).isEqualTo(CauseCategory.FRAUD_CRITICAL);
        assertThat(result.confidence()).isEqualTo(Confidence.HIGH);
        assertThat(result.primaryEvidence()).contains("CRITICAL");
    }

    @Test
    void screeningResultHit_classifiesAsAmlSanctions() {
        // AML_SANCTIONS_HIT event not present, but screeningResult=HIT
        PaymentTimeline timeline = buildTimeline(List.of(
                log("gateway",       "PAYMENT_SUBMITTED",      null, null, null, null),
                log("aml-compliance","AML_SCREENING_COMPLETE",  null, null, "HIT", "ENTITY_B")
        ));

        ClassificationResult result = classifier.classify(timeline);

        assertThat(result.category()).isEqualTo(CauseCategory.AML_SANCTIONS);
    }

    @Test
    void velocityBreach_classifiesAsFraudVelocity() {
        PaymentTimeline timeline = buildTimeline(List.of(
                log("fraud-scoring", "VELOCITY_BREACH", null, null, null, null)
        ));

        ClassificationResult result = classifier.classify(timeline);

        assertThat(result.category()).isEqualTo(CauseCategory.FRAUD_VELOCITY);
        assertThat(result.confidence()).isEqualTo(Confidence.HIGH);
    }

    @Test
    void embargoHit_classifiesAsEmbargoBlocked() {
        PaymentTimeline timeline = buildTimeline(List.of(
                log("validation-enrichment", "EMBARGO_HIT", null, null, null, null)
        ));

        ClassificationResult result = classifier.classify(timeline);

        assertThat(result.category()).isEqualTo(CauseCategory.EMBARGO_BLOCKED);
        assertThat(result.confidence()).isEqualTo(Confidence.HIGH);
    }

    @Test
    void validationFailed_classifiesAsValidationFailure_mediumConfidence() {
        PaymentTimeline timeline = buildTimeline(List.of(
                log("gateway",               "PAYMENT_SUBMITTED", null, null, null, null),
                log("validation-enrichment", "VALIDATION_FAILED", null, null, null, null)
        ));

        ClassificationResult result = classifier.classify(timeline);

        assertThat(result.category()).isEqualTo(CauseCategory.VALIDATION_FAILURE);
        assertThat(result.confidence()).isEqualTo(Confidence.MEDIUM);
    }

    @Test
    void routingFailed_classifiesAsRoutingFailure() {
        PaymentTimeline timeline = buildTimeline(List.of(
                log("gateway",           "PAYMENT_SUBMITTED", null, null, null, null),
                log("routing-execution", "ROUTING_FAILED",    null, null, null, null)
        ));

        ClassificationResult result = classifier.classify(timeline);

        assertThat(result.category()).isEqualTo(CauseCategory.ROUTING_FAILURE);
        assertThat(result.confidence()).isEqualTo(Confidence.MEDIUM);
    }

    @Test
    void errorLevelLog_classifiesAsSystemError() {
        // Use audit service (no specific failure category) to exercise the ERROR → SYSTEM_ERROR rule
        List<LogEntry> logs = List.of(
                logWithLevel("audit", null, "ERROR")
        );
        PaymentTimeline timeline = buildTimeline(logs);

        ClassificationResult result = classifier.classify(timeline);

        assertThat(result.category()).isEqualTo(CauseCategory.SYSTEM_ERROR);
        assertThat(result.confidence()).isEqualTo(Confidence.MEDIUM);
    }

    @Test
    void successfulPayment_classifiesAsUnknown_lowConfidence() {
        PaymentTimeline timeline = buildTimeline(List.of(
                log("gateway",    "PAYMENT_SUBMITTED",    null, null, null, null),
                log("settlement", "SETTLEMENT_COMPLETE",  null, null, null, null),
                log("audit",      "AUDIT_CHAIN_APPENDED", null, null, null, null)
        ));

        ClassificationResult result = classifier.classify(timeline);

        assertThat(result.category()).isEqualTo(CauseCategory.UNKNOWN);
        assertThat(result.confidence()).isEqualTo(Confidence.LOW);
    }

    @Test
    void amlTakesPriorityOverFraud() {
        // Both CRITICAL fraud AND AML sanctions hit — AML should win (rule 1 > rule 2)
        PaymentTimeline timeline = buildTimeline(List.of(
                log("fraud-scoring",  "FRAUD_SCORE_COMPUTED", 0.99, "CRITICAL", null, null),
                log("aml-compliance", "AML_SANCTIONS_HIT",    null, null, "HIT", "ENTITY_C")
        ));

        ClassificationResult result = classifier.classify(timeline);

        assertThat(result.category()).isEqualTo(CauseCategory.AML_SANCTIONS);
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private PaymentTimeline buildTimeline(List<LogEntry> logs) {
        return reconstructor.reconstruct("PAY-TEST", logs);
    }

    private LogEntry log(String service, String eventType, Double fraudScore, String riskBand,
                         String screeningResult, String listHit) {
        return new LogEntry(
                "2024-01-01T10:00:00Z", service, "INFO", "test",
                "PAY-TEST", null, null,
                eventType, null,
                fraudScore, riskBand,
                screeningResult, null, listHit,
                null, null,
                null, null, null, null
        );
    }

    private LogEntry logWithLevel(String service, String eventType, String level) {
        return new LogEntry(
                "2024-01-01T10:00:00Z", service, level, "something went wrong",
                "PAY-TEST", null, null,
                eventType, null,
                null, null,
                null, null, null,
                null, null,
                null, null, null, null
        );
    }
}
