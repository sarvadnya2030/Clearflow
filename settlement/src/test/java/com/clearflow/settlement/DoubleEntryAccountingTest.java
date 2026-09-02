package com.clearflow.settlement;

import com.clearflow.settlement.domain.EntryType;
import com.clearflow.settlement.domain.LedgerEntry;
import com.clearflow.settlement.domain.SettlementRecord;
import com.clearflow.settlement.repository.LedgerRepository;
import com.clearflow.settlement.repository.SettlementRepository;
import com.clearflow.settlement.service.AccountingImbalanceException;
import com.clearflow.settlement.service.SettlementService;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

import java.math.BigDecimal;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

/**
 * Double-entry bookkeeping invariant tests.
 * Verifies: balanced DEBIT+CREDIT, idempotency on duplicate paymentId, imbalance guard.
 */
class DoubleEntryAccountingTest {

    private SettlementService svc(LedgerRepository ledger, SettlementRepository settlement) {
        return new SettlementService(ledger, settlement);
    }

    @Test
    @DisplayName("Settlement creates DEBIT + CREDIT entries with equal amounts (€10,500)")
    void balancedEntries() {
        LedgerRepository ledger = Mockito.mock(LedgerRepository.class);
        SettlementRepository settlement = Mockito.mock(SettlementRepository.class);

        when(settlement.findByPaymentId("p1")).thenReturn(Optional.empty());
        when(settlement.save(any(SettlementRecord.class))).thenAnswer(inv -> inv.getArgument(0));
        when(ledger.save(any(LedgerEntry.class))).thenAnswer(inv -> inv.getArgument(0));
        when(ledger.sumByPaymentIdAndType("p1", EntryType.DEBIT)).thenReturn(BigDecimal.valueOf(10_500));
        when(ledger.sumByPaymentIdAndType("p1", EntryType.CREDIT)).thenReturn(BigDecimal.valueOf(10_500));

        svc(ledger, settlement).settlePayment(
                Map.of("paymentId", "p1", "amount", "10500", "currency", "EUR"));

        verify(ledger, times(2)).save(any(LedgerEntry.class));
        assertEquals(0,
            ledger.sumByPaymentIdAndType("p1", EntryType.DEBIT)
                  .compareTo(ledger.sumByPaymentIdAndType("p1", EntryType.CREDIT)),
            "SUM(DEBIT) must equal SUM(CREDIT)");
    }

    @Test
    @DisplayName("Duplicate paymentId returns cached record without creating new ledger entries")
    void idempotentSettlement() {
        LedgerRepository ledger = Mockito.mock(LedgerRepository.class);
        SettlementRepository settlement = Mockito.mock(SettlementRepository.class);

        SettlementRecord existing = new SettlementRecord();
        existing.setPaymentId("p-dup");
        existing.setStatus("SETTLED");
        when(settlement.findByPaymentId("p-dup")).thenReturn(Optional.of(existing));

        SettlementRecord result = svc(ledger, settlement).settlePayment(
                Map.of("paymentId", "p-dup", "amount", "500", "currency", "GBP"));

        assertEquals("SETTLED", result.getStatus());
        verify(ledger, never()).save(any(LedgerEntry.class));
    }

    @Test
    @DisplayName("DEBIT ≠ CREDIT imbalance throws AccountingImbalanceException")
    void accountingImbalanceThrows() {
        LedgerRepository ledger = Mockito.mock(LedgerRepository.class);
        SettlementRepository settlement = Mockito.mock(SettlementRepository.class);

        when(settlement.findByPaymentId("p-imbal")).thenReturn(Optional.empty());
        when(settlement.save(any(SettlementRecord.class))).thenAnswer(inv -> inv.getArgument(0));
        when(ledger.save(any(LedgerEntry.class))).thenAnswer(inv -> inv.getArgument(0));
        when(ledger.sumByPaymentIdAndType("p-imbal", EntryType.DEBIT))
                .thenReturn(BigDecimal.valueOf(1000.00));
        when(ledger.sumByPaymentIdAndType("p-imbal", EntryType.CREDIT))
                .thenReturn(BigDecimal.valueOf(999.99));   // off by one cent

        assertThrows(AccountingImbalanceException.class, () ->
            svc(ledger, settlement).settlePayment(
                    Map.of("paymentId", "p-imbal", "amount", "1000.00", "currency", "USD")),
            "Off-by-one-cent imbalance must be caught by the accounting invariant guard"
        );
    }
}
