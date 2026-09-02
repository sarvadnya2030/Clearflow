package com.clearflow.validation.processor;

import org.apache.camel.Exchange;
import org.apache.camel.Processor;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component
public class EmbargoPreCheckProcessor implements Processor {

    private final StringRedisTemplate redisTemplate;

    public EmbargoPreCheckProcessor(StringRedisTemplate redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    @Override
    public void process(Exchange exchange) {
        String debtorCountry = exchange.getIn().getHeader("debtorCountry", String.class);
        String creditorCountry = exchange.getIn().getHeader("creditorCountry", String.class);

        Boolean debtorEmbargoed = redisTemplate.opsForSet().isMember("embargoed:countries", debtorCountry);
        Boolean creditorEmbargoed = redisTemplate.opsForSet().isMember("embargoed:countries", creditorCountry);

        if (Boolean.TRUE.equals(debtorEmbargoed) || Boolean.TRUE.equals(creditorEmbargoed)) {
            exchange.getIn().setHeader("validation.status", "EMBARGOED");
            exchange.getIn().setHeader("rejection.reason", "EMBARGOED_COUNTRY");
            exchange.getIn().setHeader("embargo.clean", false);
        } else {
            exchange.getIn().setHeader("embargo.clean", true);
        }
    }
}
