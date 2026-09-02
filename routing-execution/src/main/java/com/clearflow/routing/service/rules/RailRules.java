package com.clearflow.routing.service.rules;

import com.clearflow.routing.domain.PaymentRail;
import com.clearflow.routing.domain.RoutingContext;
import com.clearflow.routing.service.PaymentRailRule;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.math.BigDecimal;
import java.util.Set;

@Configuration
public class RailRules {

    private static final Set<String> SEPA_COUNTRIES = Set.of("AT","BE","BG","CH","CY","CZ","DE","DK","EE","ES","FI","FR","GB","GI","GR","HR","HU","IE","IS","IT","LI","LT","LU","LV","MC","MT","NL","NO","PL","PT","RO","SE","SI","SK","SM","VA");

    @Bean
    public PaymentRailRule internalTransferRule() {
        return new PaymentRailRule() {
            public boolean matches(RoutingContext ctx) { return prefix(ctx.debtorBic()).equals(prefix(ctx.creditorBic())); }
            public PaymentRail select(RoutingContext ctx) { return PaymentRail.INTERNAL; }
            public int priority() { return 0; }
        };
    }

    @Bean
    public PaymentRailRule sepaInstantRule() {
        return new PaymentRailRule() {
            public boolean matches(RoutingContext ctx) {
                return "EUR".equals(ctx.currency()) && SEPA_COUNTRIES.contains(ctx.debtorCountry()) && SEPA_COUNTRIES.contains(ctx.creditorCountry()) && ctx.amount().compareTo(BigDecimal.valueOf(100_000)) < 0;
            }
            public PaymentRail select(RoutingContext ctx) { return PaymentRail.SEPA_INSTANT; }
            public int priority() { return 1; }
        };
    }

    @Bean
    public PaymentRailRule sepaCreditRule() {
        return new PaymentRailRule() {
            public boolean matches(RoutingContext ctx) { return "EUR".equals(ctx.currency()) && SEPA_COUNTRIES.contains(ctx.debtorCountry()) && SEPA_COUNTRIES.contains(ctx.creditorCountry()); }
            public PaymentRail select(RoutingContext ctx) { return PaymentRail.SEPA_CREDIT_TRANSFER; }
            public int priority() { return 2; }
        };
    }

    @Bean
    public PaymentRailRule fasterPaymentsRule() {
        return new PaymentRailRule() {
            public boolean matches(RoutingContext ctx) {
                return "GBP".equals(ctx.currency()) && "GB".equals(ctx.debtorCountry()) && "GB".equals(ctx.creditorCountry()) && ctx.amount().compareTo(BigDecimal.valueOf(1_000_000)) <= 0;
            }
            public PaymentRail select(RoutingContext ctx) { return PaymentRail.FASTER_PAYMENTS; }
            public int priority() { return 3; }
        };
    }

    @Bean
    public PaymentRailRule chapsRule() {
        return new PaymentRailRule() {
            public boolean matches(RoutingContext ctx) {
                return "GBP".equals(ctx.currency()) && (ctx.amount().compareTo(BigDecimal.valueOf(1_000_000)) > 0 || "CHAPS".equalsIgnoreCase(ctx.channel()));
            }
            public PaymentRail select(RoutingContext ctx) { return PaymentRail.CHAPS; }
            public int priority() { return 4; }
        };
    }

    /**
     * CHIPS — Clearing House Interbank Payments System.
     * USD high-value (≥ $1M) between CHIPS member banks.
     * Priority 5 — evaluated BEFORE FEDWIRE (6) so CHIPS members prefer CHIPS.
     * Real CHIPS member BIC prefixes sourced from The Clearing House member list.
     */
    @Bean
    public PaymentRailRule chipsRule() {
        Set<String> CHIPS_BIC_PREFIXES = Set.of(
            "CHAS", "CITI", "BOFA", "WFBI", "BNYC", "MLCO",
            "DEUT", "HSBC", "BARW", "DBNY", "SOCG", "BNPA"
        );
        return new PaymentRailRule() {
            public boolean matches(RoutingContext ctx) {
                return "USD".equals(ctx.currency())
                    && "US".equals(ctx.debtorCountry())
                    && "US".equals(ctx.creditorCountry())
                    && ctx.amount().compareTo(BigDecimal.valueOf(1_000_000)) >= 0
                    && (CHIPS_BIC_PREFIXES.contains(prefix(ctx.debtorBic()))
                        || CHIPS_BIC_PREFIXES.contains(prefix(ctx.creditorBic())));
            }
            public PaymentRail select(RoutingContext ctx) { return PaymentRail.CHIPS; }
            public int priority() { return 5; }
        };
    }

    @Bean
    public PaymentRailRule fedwireRule() {
        return new PaymentRailRule() {
            public boolean matches(RoutingContext ctx) {
                return "USD".equals(ctx.currency()) && "US".equals(ctx.debtorCountry()) && "US".equals(ctx.creditorCountry()) && ctx.amount().compareTo(BigDecimal.valueOf(1_000_000)) >= 0;
            }
            public PaymentRail select(RoutingContext ctx) { return PaymentRail.FEDWIRE; }
            public int priority() { return 6; } // fallback for non-CHIPS USD high-value
        };
    }

    @Bean
    public PaymentRailRule fedachRule() {
        return new PaymentRailRule() {
            public boolean matches(RoutingContext ctx) { return "USD".equals(ctx.currency()) && "US".equals(ctx.debtorCountry()) && "US".equals(ctx.creditorCountry()); }
            public PaymentRail select(RoutingContext ctx) { return PaymentRail.FEDACH; }
            public int priority() { return 7; } // domestic US sub-$1M
        };
    }

    @Bean
    public PaymentRailRule swiftGpiRule() {
        return new PaymentRailRule() {
            public boolean matches(RoutingContext ctx) { return ctx.crossBorder() && ctx.amount().compareTo(BigDecimal.valueOf(50_000)) >= 0; }
            public PaymentRail select(RoutingContext ctx) { return PaymentRail.SWIFT_GPI; }
            public int priority() { return 8; }
        };
    }

    @Bean
    public PaymentRailRule target2Rule() {
        return new PaymentRailRule() {
            public boolean matches(RoutingContext ctx) { return "EUR".equals(ctx.currency()) && SEPA_COUNTRIES.contains(ctx.debtorCountry()) && ctx.amount().compareTo(BigDecimal.valueOf(1_000_000)) >= 0; }
            public PaymentRail select(RoutingContext ctx) { return PaymentRail.TARGET2; }
            public int priority() { return 10; }
        };
    }

    @Bean
    public PaymentRailRule bacsRule() {
        return new PaymentRailRule() {
            public boolean matches(RoutingContext ctx) {
                return "GBP".equals(ctx.currency()) && "GB".equals(ctx.debtorCountry()) && "GB".equals(ctx.creditorCountry()) && ctx.amount().compareTo(BigDecimal.valueOf(1_000_000)) > 0;
            }
            public PaymentRail select(RoutingContext ctx) { return PaymentRail.BACS; }
            public int priority() { return 11; }
        };
    }

    @Bean
    public PaymentRailRule swiftMt103Rule() {
        return new PaymentRailRule() {
            public boolean matches(RoutingContext ctx) { return ctx.crossBorder(); }
            public PaymentRail select(RoutingContext ctx) { return PaymentRail.SWIFT_MT103; }
            public int priority() { return Integer.MAX_VALUE; }
        };
    }

    private static String prefix(String bic) {
        if (bic == null || bic.length() < 4) return "";
        return bic.substring(0, 4);
    }
}
