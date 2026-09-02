package com.clearflow.validation.domain;

import jakarta.persistence.Id;
import org.springframework.data.mongodb.core.mapping.Document;

import java.time.Instant;

@Document(collection = "payment_enrichments")
public class PaymentEnrichment {
    @Id
    private String paymentId;
    private String correlationId;
    private String debtorIban;
    private String creditorIban;
    private String correspondentBic;
    private Double indicativeFxRate;
    private String preferredRail;
    private Integer expectedSettlementHours;
    private String customerTier;
    private String kycStatus;
    private Instant enrichedAt;

    public String getPaymentId() { return paymentId; }
    public void setPaymentId(String paymentId) { this.paymentId = paymentId; }
    public String getCorrelationId() { return correlationId; }
    public void setCorrelationId(String correlationId) { this.correlationId = correlationId; }
    public String getDebtorIban() { return debtorIban; }
    public void setDebtorIban(String debtorIban) { this.debtorIban = debtorIban; }
    public String getCreditorIban() { return creditorIban; }
    public void setCreditorIban(String creditorIban) { this.creditorIban = creditorIban; }
    public String getCorrespondentBic() { return correspondentBic; }
    public void setCorrespondentBic(String correspondentBic) { this.correspondentBic = correspondentBic; }
    public Double getIndicativeFxRate() { return indicativeFxRate; }
    public void setIndicativeFxRate(Double indicativeFxRate) { this.indicativeFxRate = indicativeFxRate; }
    public String getPreferredRail() { return preferredRail; }
    public void setPreferredRail(String preferredRail) { this.preferredRail = preferredRail; }
    public Integer getExpectedSettlementHours() { return expectedSettlementHours; }
    public void setExpectedSettlementHours(Integer expectedSettlementHours) { this.expectedSettlementHours = expectedSettlementHours; }
    public String getCustomerTier() { return customerTier; }
    public void setCustomerTier(String customerTier) { this.customerTier = customerTier; }
    public String getKycStatus() { return kycStatus; }
    public void setKycStatus(String kycStatus) { this.kycStatus = kycStatus; }
    public Instant getEnrichedAt() { return enrichedAt; }
    public void setEnrichedAt(Instant enrichedAt) { this.enrichedAt = enrichedAt; }
}
