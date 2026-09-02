package com.clearflow.settlement.processor;

import com.clearflow.settlement.domain.SettlementRecord;
import com.clearflow.settlement.service.SettlementService;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import org.apache.camel.Exchange;
import org.apache.camel.Processor;
import org.springframework.stereotype.Component;

import java.util.Map;

@Component
public class SettlementProcessor implements Processor {

    private static final ObjectMapper MAPPER = new ObjectMapper().registerModule(new JavaTimeModule());

    private final SettlementService settlementService;

    public SettlementProcessor(SettlementService settlementService) {
        this.settlementService = settlementService;
    }

    @Override
    @SuppressWarnings("unchecked")
    public void process(Exchange exchange) {
        Map<String, Object> payload;
        Object body = exchange.getIn().getBody();
        if (body instanceof Map<?, ?> map) {
            payload = (Map<String, Object>) map;
        } else {
            payload = Map.of(
                    "paymentId", exchange.getIn().getHeader("paymentId", String.class),
                    "amount", exchange.getIn().getHeader("amount", String.class),
                    "currency", exchange.getIn().getHeader("currency", String.class),
                    "correlationId", exchange.getIn().getHeader("correlationId", String.class)
            );
        }
        SettlementRecord result = settlementService.settlePayment(payload);
        try {
            exchange.getIn().setBody(MAPPER.writeValueAsString(result));
        } catch (com.fasterxml.jackson.core.JsonProcessingException e) {
            throw new RuntimeException("Failed to serialize SettlementRecord", e);
        }
    }
}
