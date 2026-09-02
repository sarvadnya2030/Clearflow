package com.clearflow.compliance.controller;

import com.clearflow.common.messaging.KafkaTopics;
import com.clearflow.compliance.domain.AmlState;
import com.clearflow.compliance.domain.ScreeningRecord;
import com.clearflow.compliance.repository.ScreeningRecordRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.web.bind.annotation.*;

import java.time.Instant;
import java.util.List;
import java.util.Map;

/**
 * Real gate for AML holds/escalations: a payment stopped by
 * AMLKafkaConsumer's gate stays stopped -- no automatic retry can push it
 * through -- until a reviewer explicitly resolves it here. Resolving to
 * CLEAR replays the originally screened payload forward to
 * AML_SANCTIONS_CLEAR so it enters routing exactly as a clean payment would.
 * Resolving to REJECTED is terminal; nothing republishes it anywhere.
 */
@RestController
@RequestMapping("/api/v1/compliance")
public class ComplianceReviewController {

    private static final Logger log = LoggerFactory.getLogger(ComplianceReviewController.class);

    private final ScreeningRecordRepository repository;
    private final KafkaTemplate<String, String> kafkaTemplate;

    public ComplianceReviewController(ScreeningRecordRepository repository,
                                       @Qualifier("amlKafkaTemplate") KafkaTemplate<String, String> kafkaTemplate) {
        this.repository = repository;
        this.kafkaTemplate = kafkaTemplate;
    }

    @GetMapping("/holds")
    public ResponseEntity<List<ScreeningRecord>> pendingHolds() {
        return ResponseEntity.ok(
                repository.findByAmlStateInAndResolvedAtIsNull(List.of(AmlState.HOLD, AmlState.ESCALATED)));
    }

    public record ResolveRequest(AmlState decision, String reviewer, String note) {}

    @PostMapping("/{paymentId}/resolve")
    public ResponseEntity<?> resolve(@PathVariable String paymentId, @RequestBody ResolveRequest req) {
        ScreeningRecord record = repository.findFirstByPaymentIdOrderByCreatedAtDesc(paymentId).orElse(null);
        if (record == null) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("error", "no screening record for paymentId " + paymentId));
        }
        if (record.getAmlState() != AmlState.HOLD && record.getAmlState() != AmlState.ESCALATED) {
            return ResponseEntity.status(HttpStatus.CONFLICT).body(Map.of("error", "payment is not in HOLD/ESCALATED state, current=" + record.getAmlState()));
        }
        if (req.decision() != AmlState.CLEAR && req.decision() != AmlState.REJECTED) {
            return ResponseEntity.badRequest().body(Map.of("error", "decision must be CLEAR or REJECTED"));
        }

        record.setAmlState(req.decision());
        record.setResolvedAt(Instant.now());
        record.setResolvedBy(req.reviewer());
        record.setResolutionNote(req.note());
        repository.save(record);

        if (req.decision() == AmlState.CLEAR) {
            if (record.getOriginalPayload() == null) {
                log.error("Cannot replay paymentId={}: no stored payload", paymentId);
                return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                        .body(Map.of("error", "no stored payload to replay"));
            }
            kafkaTemplate.send(KafkaTopics.AML_SANCTIONS_CLEAR, paymentId, record.getOriginalPayload());
            log.info("AML_HOLD_RESOLVED paymentId={} decision=CLEAR reviewer={} -- replayed to routing", paymentId, req.reviewer());
        } else {
            log.info("AML_HOLD_RESOLVED paymentId={} decision=REJECTED reviewer={} -- terminal, not replayed", paymentId, req.reviewer());
        }

        return ResponseEntity.ok(record);
    }
}
