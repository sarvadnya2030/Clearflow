package com.clearflow.settlement.repository;

import com.clearflow.settlement.domain.EntryType;
import com.clearflow.settlement.domain.LedgerEntry;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.math.BigDecimal;
import java.util.List;

public interface LedgerRepository extends JpaRepository<LedgerEntry, String> {
    List<LedgerEntry> findByPaymentId(String paymentId);

    @Query("select coalesce(sum(l.amount), 0) from LedgerEntry l where l.paymentId = :paymentId and l.entryType = :type")
    BigDecimal sumByPaymentIdAndType(String paymentId, EntryType type);
}
