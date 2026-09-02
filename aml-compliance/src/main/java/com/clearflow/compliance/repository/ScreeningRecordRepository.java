package com.clearflow.compliance.repository;

import com.clearflow.compliance.domain.AmlState;
import com.clearflow.compliance.domain.ScreeningRecord;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface ScreeningRecordRepository extends JpaRepository<ScreeningRecord, String> {
    Optional<ScreeningRecord> findFirstByPaymentIdOrderByCreatedAtDesc(String paymentId);
    List<ScreeningRecord> findByAmlStateInAndResolvedAtIsNull(List<AmlState> states);
}
