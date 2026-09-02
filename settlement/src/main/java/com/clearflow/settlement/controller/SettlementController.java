package com.clearflow.settlement.controller;

import com.clearflow.settlement.domain.LedgerEntry;
import com.clearflow.settlement.domain.SettlementRecord;
import com.clearflow.settlement.repository.SettlementRepository;
import com.clearflow.settlement.service.SettlementService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.time.LocalDate;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/settlement")
public class SettlementController {

    private final SettlementRepository settlementRepository;
    private final SettlementService settlementService;

    public SettlementController(SettlementRepository settlementRepository, SettlementService settlementService) {
        this.settlementRepository = settlementRepository;
        this.settlementService = settlementService;
    }

    @GetMapping("/{paymentId}")
    public ResponseEntity<Map<String, Object>> getSettlement(@PathVariable String paymentId) {
        SettlementRecord record = settlementRepository.findByPaymentId(paymentId).orElse(null);
        if (record == null) return ResponseEntity.notFound().build();
        List<LedgerEntry> entries = settlementService.ledgerEntries(paymentId);
        return ResponseEntity.ok(Map.of("record", record, "ledgerEntries", entries));
    }

    @GetMapping("/positions")
    public ResponseEntity<List<Map<String, Object>>> positions() {
        return ResponseEntity.ok(List.of());
    }

    @GetMapping("/reconciliation/{date}")
    public ResponseEntity<Map<String, Object>> reconciliation(@PathVariable String date) {
        return ResponseEntity.ok(Map.of("date", LocalDate.parse(date), "status", "generated"));
    }
}
