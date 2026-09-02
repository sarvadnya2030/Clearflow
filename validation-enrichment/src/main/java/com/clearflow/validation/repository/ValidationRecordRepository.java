package com.clearflow.validation.repository;

import com.clearflow.validation.domain.ValidationRecord;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ValidationRecordRepository extends JpaRepository<ValidationRecord, String> {
}
