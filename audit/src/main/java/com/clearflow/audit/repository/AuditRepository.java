package com.clearflow.audit.repository;

import com.clearflow.audit.domain.AuditRecord;
import com.clearflow.audit.domain.AuditRecordKey;
import org.springframework.data.cassandra.repository.CassandraRepository;

import java.util.List;

public interface AuditRepository extends CassandraRepository<AuditRecord, AuditRecordKey> {
    List<AuditRecord> findByKeyPaymentIdOrderByKeyEventTimeAsc(String paymentId);
}
