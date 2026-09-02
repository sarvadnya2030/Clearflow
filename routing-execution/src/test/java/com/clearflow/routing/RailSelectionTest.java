package com.clearflow.routing;

import com.clearflow.routing.domain.PaymentRail;
import com.clearflow.routing.domain.RoutingContext;
import com.clearflow.routing.service.RailSelectionEngine;
import com.clearflow.routing.service.rules.RailRules;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;

/**
 * Chain-of-Responsibility rail selection tests covering all 12 payment rails.
 *
 * Priority order (lower wins): INTERNAL(0) SEPA_INSTANT(1) SEPA_CT(2)
 * FASTER_PAYMENTS(3) CHAPS(4) CHIPS(5) FEDWIRE(6) FEDACH(7) SWIFT_GPI(8)
 * TARGET2(10) BACS(11) SWIFT_MT103(MAX)
 *
 * Real BICs used: DEUTDEFFXXX (Deutsche Bank), ABNANL2AXXX (ABN AMRO),
 * CHASUS33XXX (JPMorgan Chase), CITIUS33XXX (Citibank), BARCGB22XXX (Barclays),
 * BNPAFRPPXXX (BNP Paribas), DBSSSGSGXXX (DBS Singapore).
 */
class RailSelectionTest {

    private final RailRules rules = new RailRules();

    private final RailSelectionEngine engine = new RailSelectionEngine(List.of(
            rules.internalTransferRule(),
            rules.sepaInstantRule(),
            rules.sepaCreditRule(),
            rules.fasterPaymentsRule(),
            rules.chapsRule(),
            rules.chipsRule(),
            rules.fedwireRule(),
            rules.fedachRule(),
            rules.swiftGpiRule(),
            rules.target2Rule(),
            rules.bacsRule(),
            rules.swiftMt103Rule()
    ));

    @Test
    @DisplayName("Same BIC prefix (DEUT) selects INTERNAL transfer")
    void internalTransfer() {
        assertEquals(PaymentRail.INTERNAL,
            engine.selectRail(ctx(BigDecimal.valueOf(1_000_000), "EUR", "DE", "DE", "DEUTDEFFXXX", "DEUTDEDBXXX", "INTERNAL", false)));
    }

    @Test
    @DisplayName("EUR 500 NL→DE selects SEPA_INSTANT (< €100K)")
    void sepaInstant() {
        assertEquals(PaymentRail.SEPA_INSTANT,
            engine.selectRail(ctx(BigDecimal.valueOf(500), "EUR", "NL", "DE", "ABNANL2AXXX", "DEUTDEFFXXX", "SEPA", true)));
    }

    @Test
    @DisplayName("EUR 150K FR→IT selects SEPA_CREDIT_TRANSFER (≥ €100K, below €1M)")
    void sepaCredit() {
        assertEquals(PaymentRail.SEPA_CREDIT_TRANSFER,
            engine.selectRail(ctx(BigDecimal.valueOf(150_000), "EUR", "FR", "IT", "BNPAFRPPXXX", "UNCRITMM", "SEPA", true)));
    }

    @Test
    @DisplayName("GBP 5K GB→GB selects FASTER_PAYMENTS (≤ £1M)")
    void fasterPayments() {
        assertEquals(PaymentRail.FASTER_PAYMENTS,
            engine.selectRail(ctx(BigDecimal.valueOf(5_000), "GBP", "GB", "GB", "BARCGB22XXX", "HBUKGB4BXXX", "FPS", false)));
    }

    @Test
    @DisplayName("GBP 2M GB→GB selects CHAPS (> £1M)")
    void chaps() {
        assertEquals(PaymentRail.CHAPS,
            engine.selectRail(ctx(BigDecimal.valueOf(2_000_000), "GBP", "GB", "GB", "BARCGB22XXX", "HBUKGB4BXXX", "CHAPS", false)));
    }

    @Test
    @DisplayName("USD 5M CHAS→CITI selects CHIPS (CHIPS members, priority 5 beats FEDWIRE at 6)")
    void chips() {
        // CHAS and CITI are in CHIPS_BIC_PREFIXES — CHIPS wins over FEDWIRE
        assertEquals(PaymentRail.CHIPS,
            engine.selectRail(ctx(BigDecimal.valueOf(5_000_000), "USD", "US", "US", "CHASUS33XXX", "CITIUS33XXX", "CHIPS", false)));
    }

    @Test
    @DisplayName("USD 2M non-CHIPS BICs US→US selects FEDWIRE (CHIPS rule skipped)")
    void fedwire() {
        // FNBO prefix not in CHIPS member list → falls through to FEDWIRE
        assertEquals(PaymentRail.FEDWIRE,
            engine.selectRail(ctx(BigDecimal.valueOf(2_000_000), "USD", "US", "US", "FNBOUS33XXX", "MELOUSA0XXX", "FEDWIRE", false)));
    }

    @Test
    @DisplayName("USD 50K US→US selects FEDACH (< $1M threshold)")
    void fedach() {
        assertEquals(PaymentRail.FEDACH,
            engine.selectRail(ctx(BigDecimal.valueOf(50_000), "USD", "US", "US", "CHASUS33XXX", "CITIUS33XXX", "ACH", false)));
    }

    @Test
    @DisplayName("USD 100K US→SG cross-border selects SWIFT_GPI (≥ $50K)")
    void swiftGpi() {
        assertEquals(PaymentRail.SWIFT_GPI,
            engine.selectRail(ctx(BigDecimal.valueOf(100_000), "USD", "US", "SG", "CHASUS33XXX", "DBSSSGSGXXX", "SWIFT_GPI", true)));
    }

    @Test
    @DisplayName("USD 1K US→NG cross-border below GPI threshold selects SWIFT_MT103 (fallback)")
    void swiftMt103Fallback() {
        assertEquals(PaymentRail.SWIFT_MT103,
            engine.selectRail(ctx(BigDecimal.valueOf(1_000), "USD", "US", "NG", "CHASUS33XXX", "ABNGNGLA", "SWIFT", true)));
    }

    @Test
    @DisplayName("TARGET2 rule matches EUR ≥ €1M SEPA country (evaluated in isolation)")
    void target2Isolated() {
        // TARGET2 (priority 10) is superseded by SEPA_CT (2) in the full engine.
        // Test it in isolation to verify the rule logic is correct.
        PaymentRail rail = new RailSelectionEngine(List.of(rules.target2Rule()))
                .selectRail(ctx(BigDecimal.valueOf(5_000_000), "EUR", "DE", "FR", "DEUTDEFFXXX", "BNPAFRPPXXX", "TARGET2", false));
        assertEquals(PaymentRail.TARGET2, rail);
    }

    @Test
    @DisplayName("BACS rule matches GBP > £1M GB→GB (evaluated in isolation)")
    void bacsIsolated() {
        // BACS (priority 11) is superseded by CHAPS (4) in the full engine.
        PaymentRail rail = new RailSelectionEngine(List.of(rules.bacsRule()))
                .selectRail(ctx(BigDecimal.valueOf(1_500_000), "GBP", "GB", "GB", "BARCGB22XXX", "HBUKGB4BXXX", "BACS", false));
        assertEquals(PaymentRail.BACS, rail);
    }

    private static RoutingContext ctx(BigDecimal amount, String currency, String debtorCountry,
                                      String creditorCountry, String debtorBic, String creditorBic,
                                      String channel, boolean crossBorder) {
        return new RoutingContext(amount, currency, debtorCountry, creditorCountry,
                debtorBic, creditorBic, channel, crossBorder, Map.of());
    }
}
