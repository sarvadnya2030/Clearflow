package com.clearflow.validation.processor;

import org.apache.camel.Exchange;
import org.apache.camel.Processor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;

@Component
public class CurrencyValidationProcessor implements Processor {

    private static final Logger log = LoggerFactory.getLogger(CurrencyValidationProcessor.class);
    private final JdbcTemplate jdbcTemplate;

    public CurrencyValidationProcessor(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public void process(Exchange exchange) {
        String debtorCurrency = exchange.getIn().getHeader("debtorCurrency", String.class);
        String creditorCurrency = exchange.getIn().getHeader("creditorCurrency", String.class);
        BigDecimal amount = exchange.getIn().getHeader("amount", BigDecimal.class);

        try {
            Integer count = jdbcTemplate.queryForObject(
                    "SELECT count(*) FROM supported_currency_pairs WHERE debtor_currency = ? AND creditor_currency = ? AND active = 'Y'",
                    Integer.class, debtorCurrency, creditorCurrency);
            // count = 0 means pair not configured; treat as allowed when table has no rows at all
            Integer total = jdbcTemplate.queryForObject("SELECT count(*) FROM supported_currency_pairs", Integer.class);
            boolean valid = total == null || total == 0 || (count != null && count > 0);
            exchange.getIn().setHeader("currency.valid", valid);
            if (!valid) {
                exchange.getIn().setHeader("validation.status", "INVALID");
                exchange.getIn().setHeader("rejection.reason", "UNSUPPORTED_CURRENCY_PAIR");
            }
        } catch (Exception ex) {
            log.warn("Currency pair lookup unavailable for {}/{} — allowing through: {}", debtorCurrency, creditorCurrency, ex.getMessage());
            exchange.getIn().setHeader("currency.valid", true);
        }
    }
}
