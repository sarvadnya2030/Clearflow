package com.clearflow.validation.processor;

import com.clearflow.common.domain.EnrichedPaymentEvent;
import com.clearflow.common.security.MaskedIbanSerializer;
import com.clearflow.validation.domain.PaymentEnrichment;
import com.clearflow.validation.repository.PaymentEnrichmentRepository;
import org.apache.camel.Exchange;
import org.apache.camel.Processor;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Map;

@Component
public class EnrichmentProcessor implements Processor {

    private final JdbcTemplate jdbcTemplate;
    private final MongoTemplate mongoTemplate;
    private final PaymentEnrichmentRepository enrichmentRepository;

    public EnrichmentProcessor(JdbcTemplate jdbcTemplate,
                               MongoTemplate mongoTemplate,
                               PaymentEnrichmentRepository enrichmentRepository) {
        this.jdbcTemplate = jdbcTemplate;
        this.mongoTemplate = mongoTemplate;
        this.enrichmentRepository = enrichmentRepository;
    }

    @Override
    @SuppressWarnings("unchecked")
    public void process(Exchange exchange) {
        String paymentId = exchange.getIn().getHeader("paymentId", String.class);
        String correlationId = exchange.getIn().getHeader("correlationId", String.class);
        String debtorIban = exchange.getIn().getHeader("debtorIban", String.class);
        String creditorIban = exchange.getIn().getHeader("creditorIban", String.class);
        String debtorBic = exchange.getIn().getHeader("debtorBic", String.class);
        String creditorBic = exchange.getIn().getHeader("creditorBic", String.class);
        String debtorCountry = exchange.getIn().getHeader("debtorCountry", String.class);
        String creditorCountry = exchange.getIn().getHeader("creditorCountry", String.class);
        String debtorCurrency = exchange.getIn().getHeader("debtorCurrency", String.class);
        String creditorCurrency = exchange.getIn().getHeader("creditorCurrency", String.class);
        String debtorName = exchange.getIn().getHeader("debtorName", "", String.class);
        String creditorName = exchange.getIn().getHeader("creditorName", "", String.class);
        BigDecimal amount = exchange.getIn().getHeader("amount", BigDecimal.class);

        Double fxRate = 1.0;
        try {
            List<Double> rates = jdbcTemplate.queryForList(
                    "SELECT rate FROM fx_rates WHERE from_currency = ? AND to_currency = ? LIMIT 1",
                    Double.class, debtorCurrency, creditorCurrency);
            if (!rates.isEmpty() && rates.get(0) != null) fxRate = rates.get(0);
        } catch (Exception ignored) {}

        Map<String, Object> route = Map.of(
                "preferred_rail", "SWIFT_MT103",
                "expected_settlement_hours", 24);
        try {
            List<Map<String, Object>> routes = jdbcTemplate.queryForList(
                    "SELECT preferred_rail, expected_settlement_hours FROM routing_rules WHERE currency = ? LIMIT 1",
                    debtorCurrency);
            if (!routes.isEmpty()) route = routes.get(0);
        } catch (Exception ignored) {}

        String customerTier = "RETAIL";
        String kycStatus = "VERIFIED";
        try {
            Map<String, Object> profile = mongoTemplate.findById(debtorIban, Map.class, "customer_profiles");
            if (profile != null) {
                customerTier = String.valueOf(profile.getOrDefault("customerTier", "RETAIL"));
                kycStatus = String.valueOf(profile.getOrDefault("kycStatus", "VERIFIED"));
            }
        } catch (Exception ignored) {
        }

        EnrichedPaymentEvent event = new EnrichedPaymentEvent(
                paymentId,
                correlationId,
                MaskedIbanSerializer.mask(debtorIban),
                MaskedIbanSerializer.mask(creditorIban),
                debtorBic,
                creditorBic,
                debtorCountry,
                creditorCountry,
                amount,
                debtorCurrency,
                creditorCurrency,
                String.valueOf(route.getOrDefault("preferred_rail", "SWIFT_MT103")),
                Integer.parseInt(String.valueOf(route.getOrDefault("expected_settlement_hours", 24))),
                customerTier,
                kycStatus,
                Instant.now(),
                debtorName,
                creditorName
        );

        PaymentEnrichment enrichment = new PaymentEnrichment();
        enrichment.setPaymentId(paymentId);
        enrichment.setCorrelationId(correlationId);
        enrichment.setDebtorIban(MaskedIbanSerializer.mask(debtorIban));
        enrichment.setCreditorIban(MaskedIbanSerializer.mask(creditorIban));
        enrichment.setCorrespondentBic(creditorBic);
        enrichment.setIndicativeFxRate(fxRate != null ? fxRate : 1.0);
        enrichment.setPreferredRail(event.preferredRail());
        enrichment.setExpectedSettlementHours(event.expectedSettlementHours());
        enrichment.setCustomerTier(customerTier);
        enrichment.setKycStatus(kycStatus);
        enrichment.setEnrichedAt(Instant.now());
        enrichmentRepository.save(enrichment);

        exchange.getIn().setBody(event);
        exchange.getIn().setHeader("validation.status", exchange.getIn().getHeader("validation.status", "VALID", String.class));
    }
}
