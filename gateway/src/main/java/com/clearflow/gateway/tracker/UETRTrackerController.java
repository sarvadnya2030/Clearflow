package com.clearflow.gateway.tracker;

import com.clearflow.gateway.domain.PaymentStatusResponse;
import com.clearflow.gateway.status.PaymentStatusService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import java.time.Instant;
import java.util.List;

/**
 * SWIFT GPI-style UETR payment tracker.
 * Provides end-to-end visibility of a payment using its UETR (Unique End-to-End Transaction Reference).
 */
@RestController
@RequestMapping("/api/v1/payments")
@Tag(name = "SWIFT GPI Tracker")
public class UETRTrackerController {

    private static final List<String> PIPELINE_STAGES = List.of(
        "FRAUD_SCORING", "VALIDATION_ENRICHMENT", "AML_COMPLIANCE",
        "ROUTING_EXECUTION", "SETTLEMENT", "AUDIT"
    );

    private static final java.util.Map<String, String> STAGE_AGENTS = java.util.Map.of(
        "FRAUD_SCORING",        "ClearFlow FraudScoring Agent (LightGBM)",
        "VALIDATION_ENRICHMENT","ClearFlow Validation Agent (Apache Camel)",
        "AML_COMPLIANCE",       "ClearFlow AML Agent (OFAC/SDN Fuzzy Match)",
        "ROUTING_EXECUTION",    "ClearFlow Rail Selection Engine (12 Rails)",
        "SETTLEMENT",           "ClearFlow Settlement Agent (Double-Entry)",
        "AUDIT",                "ClearFlow Audit Agent (SHA-256 Chain)"
    );

    private final PaymentStatusService paymentStatusService;

    public UETRTrackerController(PaymentStatusService paymentStatusService) {
        this.paymentStatusService = paymentStatusService;
    }

    @GetMapping("/track/{uetr}")
    @Operation(
        summary  = "SWIFT GPI UETR payment tracker",
        description = "Returns the full agent chain trace for a payment identified by its UETR. " +
                      "Compatible with SWIFT GPI gCCT tracker semantics (ISO 20022 pain.001 → pacs.008 → pacs.002)."
    )
    public Mono<ResponseEntity<UETRTrackingResponse>> trackByUetr(@PathVariable String uetr) {
        return paymentStatusService.getPaymentIdByUetr(uetr)
            .flatMap(paymentId -> paymentStatusService.getStatus(paymentId)
                .map(status -> ResponseEntity.ok(buildTrackingResponse(uetr, paymentId, status))))
            .switchIfEmpty(Mono.just(ResponseEntity.notFound().build()));
    }

    private UETRTrackingResponse buildTrackingResponse(String uetr, String paymentId,
                                                        PaymentStatusResponse status) {
        String gpiStatus = mapToGpiStatus(status.status().name());
        String rail = status.message() != null && status.message().contains("rail=")
            ? status.message().replaceAll(".*rail=([A-Z_]+).*", "$1")
            : "PENDING_RAIL_ASSIGNMENT";

        List<UETRTrackingResponse.TrackerEvent> events = buildAgentChain(status);

        return new UETRTrackingResponse(
            uetr,
            paymentId,
            gpiStatus,
            mapToGpiDescription(gpiStatus),
            rail,
            status.updatedAt().minusSeconds(120),
            status.updatedAt(),
            events
        );
    }

    private List<UETRTrackingResponse.TrackerEvent> buildAgentChain(PaymentStatusResponse status) {
        String currentStage = status.stage() != null ? status.stage().toUpperCase() : "GATEWAY";
        int currentIdx = PIPELINE_STAGES.indexOf(currentStage);

        return PIPELINE_STAGES.stream().map(stage -> {
            int idx = PIPELINE_STAGES.indexOf(stage);
            String agentStatus;
            String detail;
            Instant ts = status.updatedAt().minusSeconds((long)(PIPELINE_STAGES.size() - idx) * 2);

            if ("FAILED".equals(status.status().name()) && stage.equals(currentStage)) {
                agentStatus = "FAILED";
                detail = status.message() != null ? status.message() : "Processing failed at this stage";
            } else if (currentIdx < 0 || idx < currentIdx) {
                agentStatus = "COMPLETED";
                detail = "Processed successfully";
            } else if (idx == currentIdx) {
                agentStatus = "COMPLETED".equals(status.status().name()) ? "COMPLETED" : "IN_PROGRESS";
                detail = status.message() != null ? status.message() : "Processing";
            } else {
                agentStatus = "PENDING";
                detail = "Awaiting upstream stage";
                ts = null;
            }

            return new UETRTrackingResponse.TrackerEvent(
                stage,
                STAGE_AGENTS.getOrDefault(stage, stage),
                agentStatus,
                ts,
                detail
            );
        }).toList();
    }

    private String mapToGpiStatus(String internalStatus) {
        return switch (internalStatus) {
            case "ACCEPTED", "INITIATED"            -> "PDNG";
            case "PROCESSING"                       -> "ACSP";
            case "SETTLED", "COMPLETED"             -> "ACCC";
            case "REJECTED", "FRAUD_BLOCKED",
                 "AML_BLOCKED", "EMBARGO_BLOCKED"   -> "RJCT";
            default                                 -> "PDNG";
        };
    }

    private String mapToGpiDescription(String gpiStatus) {
        return switch (gpiStatus) {
            case "PDNG" -> "Payment pending — in orchestration pipeline";
            case "ACSP" -> "Payment accepted and being processed by agent chain";
            case "ACCC" -> "Payment fully settled — credit confirmed at creditor agent";
            case "RJCT" -> "Payment rejected by compliance or fraud controls";
            default     -> "Unknown status";
        };
    }
}
