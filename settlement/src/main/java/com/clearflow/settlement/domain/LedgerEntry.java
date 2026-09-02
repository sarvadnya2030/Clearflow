package com.clearflow.settlement.domain;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;

@Entity
@Table(name = "ledger_entries")
public class LedgerEntry {
    @Id
    private String id;
    private String paymentId;
    private String accountId;
    @Enumerated(EnumType.STRING)
    private EntryType entryType;
    private BigDecimal amount;
    private String currency;
    private LocalDate valueDate;
    private Instant bookingDate;
    private String reference;
    private String correlationId;
    private Instant createdAt;
    private Instant updatedAt;
    @Version
    private Long version;

    @PrePersist
    void onCreate() {
        if (id == null) id = java.util.UUID.randomUUID().toString();
        if (bookingDate == null) bookingDate = Instant.now();
        createdAt = Instant.now();
        updatedAt = Instant.now();
    }

    @PreUpdate
    void onUpdate() { updatedAt = Instant.now(); }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getPaymentId() { return paymentId; }
    public void setPaymentId(String paymentId) { this.paymentId = paymentId; }
    public String getAccountId() { return accountId; }
    public void setAccountId(String accountId) { this.accountId = accountId; }
    public EntryType getEntryType() { return entryType; }
    public void setEntryType(EntryType entryType) { this.entryType = entryType; }
    public BigDecimal getAmount() { return amount; }
    public void setAmount(BigDecimal amount) { this.amount = amount; }
    public String getCurrency() { return currency; }
    public void setCurrency(String currency) { this.currency = currency; }
    public LocalDate getValueDate() { return valueDate; }
    public void setValueDate(LocalDate valueDate) { this.valueDate = valueDate; }
    public String getReference() { return reference; }
    public void setReference(String reference) { this.reference = reference; }
    public String getCorrelationId() { return correlationId; }
    public void setCorrelationId(String correlationId) { this.correlationId = correlationId; }
}
