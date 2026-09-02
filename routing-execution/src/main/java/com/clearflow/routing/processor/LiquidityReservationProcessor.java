package com.clearflow.routing.processor;

import com.clearflow.routing.service.LiquidityReservationService;
import org.apache.camel.Exchange;
import org.apache.camel.Processor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;

@Component
public class LiquidityReservationProcessor implements Processor {

    private static final Logger log = LoggerFactory.getLogger(LiquidityReservationProcessor.class);
    private final LiquidityReservationService liquidityReservationService;

    public LiquidityReservationProcessor(LiquidityReservationService liquidityReservationService) {
        this.liquidityReservationService = liquidityReservationService;
    }

    @Override
    public void process(Exchange exchange) {
        String paymentId = exchange.getIn().getHeader("paymentId", String.class);
        String currency = exchange.getIn().getHeader("currency", String.class);
        String rail = exchange.getIn().getHeader("rail.selected", String.class);
        BigDecimal amount = exchange.getIn().getHeader("amount", BigDecimal.class);

        log.info("LIQUIDITY_CHECK_START currency={} amount={} rail={}", currency, amount, rail);
        MDC.put("liquidity.reserved", "false");

        try {
            var result = liquidityReservationService.reserve(currency, amount, paymentId, rail);
            exchange.getIn().setHeader("liquidity.reserved", true);
            exchange.getIn().setHeader("nostro.accountId", result.accountId());
            exchange.getIn().setHeader("reservation.id", result.reservationId());

            MDC.put("liquidity.reserved", "true");
            MDC.put("liquidity.accountId", result.accountId());
            log.info("LIQUIDITY_RESERVED reservationId={} accountId={} remainingBalance={}",
                    result.reservationId(), result.accountId(), result.availableAfter());
        } catch (Exception ex) {
            exchange.getIn().setHeader("liquidity.reserved", false);
            exchange.getIn().setHeader("liquidity.error", ex.getMessage());
            log.error("LIQUIDITY_FAILED currency={} amount={} error={}", currency, amount, ex.getMessage());
        } finally {
            MDC.remove("liquidity.reserved");
            MDC.remove("liquidity.accountId");
        }
    }
}
