package com.clearflow.compliance.domain;

import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "screening_results")
public class ScreeningRecord {
    @Id
    private String id;
    private String paymentId;
    private String correlationId;
    private String debtorName;
    private String creditorName;
    private String debtorMatchType;
    private Double debtorMatchScore;
    private String debtorMatchedEntity;
    private String debtorListName;
    private String creditorMatchType;
    private Double creditorMatchScore;
    private String creditorMatchedEntity;
    private String creditorListName;
    private String overallResult;
    private String reviewRequired;
    @Enumerated(EnumType.STRING)
    private AmlState amlState;
    @Lob
    private String originalPayload;
    private Instant resolvedAt;
    private String resolvedBy;
    private String resolutionNote;
    private Instant screenedAt;
    private Instant createdAt;
    private Instant updatedAt;
    @Version
    private Long version;

    @PrePersist
    void onCreate() {
        if (id == null) id = java.util.UUID.randomUUID().toString();
        createdAt = Instant.now();
        updatedAt = Instant.now();
        if (screenedAt == null) screenedAt = Instant.now();
    }

    @PreUpdate
    void onUpdate() { updatedAt = Instant.now(); }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getPaymentId() { return paymentId; }
    public void setPaymentId(String paymentId) { this.paymentId = paymentId; }
    public String getCorrelationId() { return correlationId; }
    public void setCorrelationId(String correlationId) { this.correlationId = correlationId; }
    public String getDebtorName() { return debtorName; }
    public void setDebtorName(String debtorName) { this.debtorName = debtorName; }
    public String getCreditorName() { return creditorName; }
    public void setCreditorName(String creditorName) { this.creditorName = creditorName; }
    public String getDebtorMatchType() { return debtorMatchType; }
    public void setDebtorMatchType(String debtorMatchType) { this.debtorMatchType = debtorMatchType; }
    public Double getDebtorMatchScore() { return debtorMatchScore; }
    public void setDebtorMatchScore(Double debtorMatchScore) { this.debtorMatchScore = debtorMatchScore; }
    public String getDebtorMatchedEntity() { return debtorMatchedEntity; }
    public void setDebtorMatchedEntity(String debtorMatchedEntity) { this.debtorMatchedEntity = debtorMatchedEntity; }
    public String getDebtorListName() { return debtorListName; }
    public void setDebtorListName(String debtorListName) { this.debtorListName = debtorListName; }
    public String getCreditorMatchType() { return creditorMatchType; }
    public void setCreditorMatchType(String creditorMatchType) { this.creditorMatchType = creditorMatchType; }
    public Double getCreditorMatchScore() { return creditorMatchScore; }
    public void setCreditorMatchScore(Double creditorMatchScore) { this.creditorMatchScore = creditorMatchScore; }
    public String getCreditorMatchedEntity() { return creditorMatchedEntity; }
    public void setCreditorMatchedEntity(String creditorMatchedEntity) { this.creditorMatchedEntity = creditorMatchedEntity; }
    public String getCreditorListName() { return creditorListName; }
    public void setCreditorListName(String creditorListName) { this.creditorListName = creditorListName; }
    public String getOverallResult() { return overallResult; }
    public void setOverallResult(String overallResult) { this.overallResult = overallResult; }
    public String getReviewRequired() { return reviewRequired; }
    public void setReviewRequired(String reviewRequired) { this.reviewRequired = reviewRequired; }
    public AmlState getAmlState() { return amlState; }
    public void setAmlState(AmlState amlState) { this.amlState = amlState; }
    public String getOriginalPayload() { return originalPayload; }
    public void setOriginalPayload(String originalPayload) { this.originalPayload = originalPayload; }
    public Instant getResolvedAt() { return resolvedAt; }
    public void setResolvedAt(Instant resolvedAt) { this.resolvedAt = resolvedAt; }
    public String getResolvedBy() { return resolvedBy; }
    public void setResolvedBy(String resolvedBy) { this.resolvedBy = resolvedBy; }
    public String getResolutionNote() { return resolutionNote; }
    public void setResolutionNote(String resolutionNote) { this.resolutionNote = resolutionNote; }
}
