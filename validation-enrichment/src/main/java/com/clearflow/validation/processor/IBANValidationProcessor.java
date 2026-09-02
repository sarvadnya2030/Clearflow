package com.clearflow.validation.processor;

import org.apache.camel.Exchange;
import org.apache.camel.Processor;
import org.iban4j.IbanUtil;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

import java.util.Set;

@Component
public class IBANValidationProcessor implements Processor {

    private static final Set<String> SUPPORTED_COUNTRIES = Set.of("NL", "DE", "FR", "GB", "US", "ES", "IT", "BE", "CH", "JP", "SG", "AT", "AU", "CA", "SE", "NO", "DK", "FI", "PL", "CZ", "HU", "PT", "IE", "LU", "SK", "SI", "HR", "BG", "RO");
    private final StringRedisTemplate redisTemplate;

    public IBANValidationProcessor(StringRedisTemplate redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    @Override
    public void process(Exchange exchange) {
        String debtorIban = exchange.getIn().getHeader("debtorIban", String.class);
        String creditorIban = exchange.getIn().getHeader("creditorIban", String.class);
        try {
            if (debtorIban == null || creditorIban == null) throw new IllegalArgumentException("NULL_IBAN");
            boolean debtorMasked = debtorIban.contains("****");
            boolean creditorMasked = creditorIban.contains("****");
            if (!debtorMasked) IbanUtil.validate(debtorIban);
            if (!creditorMasked) IbanUtil.validate(creditorIban);
            if (!SUPPORTED_COUNTRIES.contains(debtorIban.substring(0, 2)) || !SUPPORTED_COUNTRIES.contains(creditorIban.substring(0, 2))) {
                throw new IllegalArgumentException("UNSUPPORTED_IBAN_COUNTRY");
            }
            Boolean blacklisted = redisTemplate.opsForSet().isMember("blacklist:ibans", debtorIban);
            if (Boolean.TRUE.equals(blacklisted)) {
                throw new IllegalArgumentException("BLACKLISTED_IBAN");
            }
            exchange.getIn().setHeader("iban.valid", true);
        } catch (Exception ex) {
            exchange.getIn().setHeader("iban.valid", false);
            exchange.getIn().setHeader("validation.status", "INVALID");
            exchange.getIn().setHeader("rejection.reason", ex.getMessage());
        }
    }
}
