package com.clearflow.validation.processor;

import org.apache.camel.Exchange;
import org.apache.camel.Processor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component
public class BICValidationProcessor implements Processor {

    private static final Logger log = LoggerFactory.getLogger(BICValidationProcessor.class);
    private final JdbcTemplate jdbcTemplate;

    public BICValidationProcessor(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public void process(Exchange exchange) {
        String creditorBic = exchange.getIn().getHeader("creditorBic", String.class);
        boolean formatOk = creditorBic != null && creditorBic.matches("[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?");
        boolean known = false;
        if (formatOk) {
            try {
                Integer count = jdbcTemplate.queryForObject("SELECT count(*) FROM correspondent_banks WHERE bic = ?", Integer.class, creditorBic);
                known = count != null && count > 0;
            } catch (Exception ex) {
                log.warn("BIC lookup failed for {}", creditorBic, ex);
            }
        }
        if (!known) {
            log.debug("Unknown correspondent BIC={}, processing continues", creditorBic);
        }
        exchange.getIn().setHeader("bic.known", known);
        exchange.getIn().setHeader("bic.valid", formatOk);
    }
}
