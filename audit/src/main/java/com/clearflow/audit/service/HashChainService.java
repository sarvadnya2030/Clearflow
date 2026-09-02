package com.clearflow.audit.service;

import com.clearflow.audit.domain.AuditRecord;
import com.clearflow.audit.domain.AuditRecordKey;
import com.clearflow.audit.domain.ChainVerificationResult;
import com.clearflow.audit.repository.AuditRepository;
import org.apache.commons.codec.binary.Hex;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

@Service
public class HashChainService {

    private static final Logger log = LoggerFactory.getLogger(HashChainService.class);
    private static final String INSTITUTION_ID = "CLEARFLOW";
    private static final String GENESIS_HASH = sha256Static("CLEARFLOW-GENESIS-BLOCK-2024-" + INSTITUTION_ID);
    private final AuditRepository auditRepository;

    public HashChainService(AuditRepository auditRepository) {
        this.auditRepository = auditRepository;
    }

    public AuditRecord createRecord(String paymentId, String eventType, String eventData) {
        List<AuditRecord> records = auditRepository.findByKeyPaymentIdOrderByKeyEventTimeAsc(paymentId);
        String previousHash = records.isEmpty() ? GENESIS_HASH : records.get(records.size() - 1).getCurrentHash();
        long blockHeight = records.size() + 1L;
        Instant timestamp = Instant.now();
        String currentHash = sha256(eventData + previousHash + timestamp.toEpochMilli() + paymentId);

        AuditRecord record = new AuditRecord();
        record.setKey(new AuditRecordKey(paymentId, timestamp));
        record.setId(UUID.randomUUID());
        record.setEventType(eventType);
        record.setEventData(eventData);
        record.setPreviousHash(previousHash);
        record.setCurrentHash(currentHash);
        record.setBlockHeight(blockHeight);
        record.setServiceSource(extractServiceSource(eventType));
        record.setRetentionYears(7);

        MDC.put("paymentId", paymentId);
        try {
            log.info("AUDIT_CHAIN_APPENDED paymentId={} blockHeight={} eventType={} hash={}",
                    paymentId, blockHeight, eventType, currentHash.substring(0, 16));
        } finally {
            MDC.remove("paymentId");
        }
        return record;
    }

    public ChainVerificationResult verifyChain(String paymentId) {
        List<AuditRecord> records = auditRepository.findByKeyPaymentIdOrderByKeyEventTimeAsc(paymentId);
        if (records.isEmpty()) {
            return ChainVerificationResult.empty(paymentId);
        }

        String expectedPrevious = GENESIS_HASH;
        for (int i = 0; i < records.size(); i++) {
            AuditRecord record = records.get(i);
            if (!expectedPrevious.equals(record.getPreviousHash())) {
                return new ChainVerificationResult(false, paymentId, records.size(), GENESIS_HASH, records.get(records.size() - 1).getCurrentHash(), i + 1, Instant.now());
            }
            String recomputed = sha256(record.getEventData() + record.getPreviousHash() + record.getKey().getEventTime().toEpochMilli() + paymentId);
            if (!recomputed.equals(record.getCurrentHash())) {
                return new ChainVerificationResult(false, paymentId, records.size(), GENESIS_HASH, records.get(records.size() - 1).getCurrentHash(), i + 1, Instant.now());
            }
            expectedPrevious = record.getCurrentHash();
        }

        return new ChainVerificationResult(true, paymentId, records.size(), GENESIS_HASH, records.get(records.size() - 1).getCurrentHash(), null, Instant.now());
    }

    private String extractServiceSource(String eventType) {
        if (eventType == null) return "unknown";
        if (eventType.contains("initiated")) return "gateway";
        if (eventType.contains("fraud")) return "fraud-scoring";
        if (eventType.contains("aml")) return "aml-compliance";
        if (eventType.contains("settled")) return "settlement";
        return "orchestration";
    }

    private String sha256(String input) {
        return sha256Static(input);
    }

    private static String sha256Static(String input) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return Hex.encodeHexString(digest.digest(input.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception ex) {
            throw new IllegalStateException(ex);
        }
    }
}
