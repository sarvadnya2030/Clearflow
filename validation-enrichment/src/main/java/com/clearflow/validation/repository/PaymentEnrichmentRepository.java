package com.clearflow.validation.repository;

import com.clearflow.validation.domain.PaymentEnrichment;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface PaymentEnrichmentRepository extends MongoRepository<PaymentEnrichment, String> {
}
