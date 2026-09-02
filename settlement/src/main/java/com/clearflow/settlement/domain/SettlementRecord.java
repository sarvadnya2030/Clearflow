package com.clearflow.settlement.domain;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Table(name = "settlement_records")
public class SettlementRecord {
    @Id
    private String id;
    private String paymentId;
    private String rail;
    private String status;
    private boolean finalized;
    private Instant finalizedAt;
    private Instant settledAt;
    private String debtorIbanMasked;
    private String creditorIbanMasked;
    private BigDecimal amount;
    private String currency;
    private String correlationId;
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
    void onUpdate() { updatedAt = Instant.now(); }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getPaymentId() { return paymentId; }
    public void setPaymentId(String paymentId) { this.paymentId = paymentId; }
    public String getRail() { return rail; }
    public void setRail(String rail) { this.rail = rail; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    public boolean isFinalized() { return finalized; }
    public void setFinalized(boolean finalized) { this.finalized = finalized; }
    public Instant getFinalizedAt() { return finalizedAt; }
    public void setFinalizedAt(Instant finalizedAt) { this.finalizedAt = finalizedAt; }
    public Instant getSettledAt() { return settledAt; }
    public void setSettledAt(Instant settledAt) { this.settledAt = settledAt; }
    public String getDebtorIbanMasked() { return debtorIbanMasked; }
    public void setDebtorIbanMasked(String debtorIbanMasked) { this.debtorIbanMasked = debtorIbanMasked; }
    public String getCreditorIbanMasked() { return creditorIbanMasked; }
    public void setCreditorIbanMasked(String creditorIbanMasked) { this.creditorIbanMasked = creditorIbanMasked; }
    public BigDecimal getAmount() { return amount; }
    public void setAmount(BigDecimal amount) { this.amount = amount; }
    public String getCurrency() { return currency; }
    public void setCurrency(String currency) { this.currency = currency; }
    public String getCorrelationId() { return correlationId; }
    public void setCorrelationId(String correlationId) { this.correlationId = correlationId; }
}
