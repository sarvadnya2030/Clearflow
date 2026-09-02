package com.clearflow.audit.controller;

import com.clearflow.audit.domain.AuditRecord;
import com.clearflow.audit.domain.ChainVerificationResult;
import com.clearflow.audit.repository.AuditRepository;
import com.clearflow.audit.service.HashChainService;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/audit")
public class AuditController {

    private final AuditRepository auditRepository;
    private final HashChainService hashChainService;

    public AuditController(AuditRepository auditRepository, HashChainService hashChainService) {
        this.auditRepository = auditRepository;
        this.hashChainService = hashChainService;
    }

    @GetMapping("/{paymentId}")
    public ResponseEntity<List<AuditRecord>> getTimeline(@PathVariable String paymentId) {
        return ResponseEntity.ok(auditRepository.findByKeyPaymentIdOrderByKeyEventTimeAsc(paymentId));
    }

    @GetMapping("/{paymentId}/verify")
    public ResponseEntity<ChainVerificationResult> verify(@PathVariable String paymentId) {
        return ResponseEntity.ok(hashChainService.verifyChain(paymentId));
    }

    @GetMapping("/{paymentId}/export")
    public ResponseEntity<Map<String, Object>> export(@PathVariable String paymentId) {
        List<AuditRecord> records = auditRepository.findByKeyPaymentIdOrderByKeyEventTimeAsc(paymentId);
        ChainVerificationResult verification = hashChainService.verifyChain(paymentId);
        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=\"audit_" + paymentId + ".json\"")
                .contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("paymentId", paymentId, "records", records, "verification", verification));
    }
}
