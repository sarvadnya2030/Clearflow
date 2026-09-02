package com.clearflow.routing.processor;

import com.clearflow.routing.domain.PaymentRail;
import com.clearflow.routing.domain.RoutingContext;
import com.clearflow.routing.service.RailSelectionEngine;
import org.apache.camel.Exchange;
import org.apache.camel.Processor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.util.Map;

@Component
public class RailSelectionProcessor implements Processor {

    private static final Logger log = LoggerFactory.getLogger(RailSelectionProcessor.class);
    private final RailSelectionEngine railSelectionEngine;

    public RailSelectionProcessor(RailSelectionEngine railSelectionEngine) {
        this.railSelectionEngine = railSelectionEngine;
    }

    @Override
    public void process(Exchange exchange) {
        BigDecimal amount = exchange.getIn().getHeader("amount", BigDecimal.class);
        String currency = exchange.getIn().getHeader("currency", String.class);
        String debtorCountry = exchange.getIn().getHeader("debtorCountry", String.class);
        String creditorCountry = exchange.getIn().getHeader("creditorCountry", String.class);
        String channel = exchange.getIn().getHeader("channel", String.class);

        log.info("RAIL_SELECTION_START amount={} currency={} {}→{} channel={}",
                amount, currency, debtorCountry, creditorCountry, channel);

        RoutingContext ctx = new RoutingContext(
                amount,
                currency,
                debtorCountry,
                creditorCountry,
                exchange.getIn().getHeader("debtorBic", String.class),
                exchange.getIn().getHeader("creditorBic", String.class),
                channel,
                true,
                Map.of()
        );
        PaymentRail rail = railSelectionEngine.selectRail(ctx);
        exchange.getIn().setHeader("rail.selected", rail.name());
        exchange.getIn().setHeader("rail.expectedSettlementTime", rail.getExpectedSettlementTime());

        MDC.put("rail.selected", rail.name());
        log.info("RAIL_SELECTED rail={} expectedSettlementTime={}", rail.name(), rail.getExpectedSettlementTime());
        MDC.remove("rail.selected");
    }
}
