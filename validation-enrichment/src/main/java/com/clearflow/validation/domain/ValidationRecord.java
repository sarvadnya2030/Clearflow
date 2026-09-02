package com.clearflow.validation.domain;

import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "validation_records")
public class ValidationRecord {
    @Id
    private String id;
    private String paymentId;
    private String correlationId;
    private String validationStatus;
    private String rejectionReason;
    private String ibanValid;
    private String bicValid;
    private String currencyValid;
    private String embargoClean;
    private Instant validatedAt;
    private Instant enrichedAt;
    private Instant createdAt;
    private Instant updatedAt;
    @Version
    private Long version;

    @PrePersist
    void onCreate() {
        if (id == null) id = java.util.UUID.randomUUID().toString();
        createdAt = Instant.now();
        updatedAt = Instant.now();
    }

    @PreUpdate
    void onUpdate() {
        updatedAt = Instant.now();
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getPaymentId() { return paymentId; }
    public void setPaymentId(String paymentId) { this.paymentId = paymentId; }
    public String getCorrelationId() { return correlationId; }
    public void setCorrelationId(String correlationId) { this.correlationId = correlationId; }
    public String getValidationStatus() { return validationStatus; }
    public void setValidationStatus(String validationStatus) { this.validationStatus = validationStatus; }
    public String getRejectionReason() { return rejectionReason; }
    public void setRejectionReason(String rejectionReason) { this.rejectionReason = rejectionReason; }
    public String getIbanValid() { return ibanValid; }
    public void setIbanValid(String ibanValid) { this.ibanValid = ibanValid; }
    public String getBicValid() { return bicValid; }
    public void setBicValid(String bicValid) { this.bicValid = bicValid; }
    public String getCurrencyValid() { return currencyValid; }
    public void setCurrencyValid(String currencyValid) { this.currencyValid = currencyValid; }
    public String getEmbargoClean() { return embargoClean; }
    public void setEmbargoClean(String embargoClean) { this.embargoClean = embargoClean; }
    public Instant getValidatedAt() { return validatedAt; }
    public void setValidatedAt(Instant validatedAt) { this.validatedAt = validatedAt; }
    public Instant getEnrichedAt() { return enrichedAt; }
    public void setEnrichedAt(Instant enrichedAt) { this.enrichedAt = enrichedAt; }
}
