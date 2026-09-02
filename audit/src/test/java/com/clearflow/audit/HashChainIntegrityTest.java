package com.clearflow.audit;

import com.clearflow.audit.domain.AuditRecord;
import com.clearflow.audit.repository.AuditRepository;
import com.clearflow.audit.service.HashChainService;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.when;

/**
 * SHA-256 hash chain tamper-evidence tests.
 * Validates Genesis block, multi-event chains, tamper detection, and cross-payment isolation.
 */
class HashChainIntegrityTest {

    @Test
    @DisplayName("Single generated record verifies as valid chain")
    void singleRecordValid() {
        AuditRepository repository = Mockito.mock(AuditRepository.class);
        when(repository.findByKeyPaymentIdOrderByKeyEventTimeAsc("p1")).thenReturn(new ArrayList<>());
        HashChainService service = new HashChainService(repository);
        AuditRecord record = service.createRecord("p1", "clearflow.payment.initiated", "{\"paymentId\":\"p1\"}");
        when(repository.findByKeyPaymentIdOrderByKeyEventTimeAsc("p1")).thenReturn(List.of(record));
        var result = service.verifyChain("p1");
        assertTrue(result.valid());
        assertEquals(1, result.totalEvents());
    }

    @Test
    @DisplayName("Five-event pipeline chain (initiated→fraud→aml→routed→settled) remains valid")
    void multiEventChainValid() {
        AuditRepository repository = Mockito.mock(AuditRepository.class);
        HashChainService service = new HashChainService(repository);
        List<AuditRecord> chain = new ArrayList<>();

        String[] events = {
            "clearflow.payment.initiated",
            "clearflow.fraud.evaluated",
            "clearflow.aml.sanctions.clear",
            "clearflow.payment.routed",
            "clearflow.payment.settled"
        };

        for (int i = 0; i < events.length; i++) {
            when(repository.findByKeyPaymentIdOrderByKeyEventTimeAsc("p-chain"))
                    .thenReturn(List.copyOf(chain));
            chain.add(service.createRecord("p-chain", events[i], "{\"seq\":" + i + "}"));
        }

        when(repository.findByKeyPaymentIdOrderByKeyEventTimeAsc("p-chain")).thenReturn(chain);
        var result = service.verifyChain("p-chain");
        assertTrue(result.valid(), "Full 5-event chain must be valid");
        assertEquals(5, result.totalEvents());
        assertNotNull(result.latestHash());
    }

    @Test
    @DisplayName("Payload tamper at block 2 breaks chain — tamperDetectedAtBlock returns 2")
    void tamperDetectedAtBlock2() {
        AuditRepository repository = Mockito.mock(AuditRepository.class);
        HashChainService service = new HashChainService(repository);
        List<AuditRecord> chain = new ArrayList<>();

        for (int i = 0; i < 3; i++) {
            when(repository.findByKeyPaymentIdOrderByKeyEventTimeAsc("p-tamper"))
                    .thenReturn(List.copyOf(chain));
            chain.add(service.createRecord("p-tamper", "clearflow.event." + i, "{\"seq\":" + i + "}"));
        }

        // Tamper: modify payload of block 2 without recomputing hashes
        chain.get(1).setEventData("{\"TAMPERED\":true}");

        when(repository.findByKeyPaymentIdOrderByKeyEventTimeAsc("p-tamper")).thenReturn(chain);
        var result = service.verifyChain("p-tamper");

        assertFalse(result.valid(), "Chain must be invalid after payload tamper");
        assertNotNull(result.tamperDetectedAtBlock());
        assertEquals(2, result.tamperDetectedAtBlock(), "Tamper must be detected at block 2");
    }

    @Test
    @DisplayName("Chain verification for p2 does not affect p1 chain (cross-payment isolation)")
    void crossPaymentIsolation() {
        AuditRepository repository = Mockito.mock(AuditRepository.class);
        HashChainService service = new HashChainService(repository);

        when(repository.findByKeyPaymentIdOrderByKeyEventTimeAsc("p-a")).thenReturn(new ArrayList<>());
        AuditRecord r1 = service.createRecord("p-a", "clearflow.payment.initiated", "{\"id\":\"p-a\"}");
        when(repository.findByKeyPaymentIdOrderByKeyEventTimeAsc("p-a")).thenReturn(List.of(r1));

        when(repository.findByKeyPaymentIdOrderByKeyEventTimeAsc("p-b")).thenReturn(new ArrayList<>());
        AuditRecord r2 = service.createRecord("p-b", "clearflow.payment.initiated", "{\"id\":\"p-b\"}");
        when(repository.findByKeyPaymentIdOrderByKeyEventTimeAsc("p-b")).thenReturn(List.of(r2));

        assertTrue(service.verifyChain("p-a").valid());
        assertTrue(service.verifyChain("p-b").valid());
        assertNotEquals(r1.getCurrentHash(), r2.getCurrentHash(),
                "Different paymentIds must produce different hashes");
    }
}
