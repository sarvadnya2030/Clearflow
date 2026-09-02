package com.clearflow.gateway.simulator;

import com.clearflow.common.domain.PaymentInitiatedEvent;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.temporal.ChronoUnit;
import java.util.Random;
import java.util.UUID;

/**
 * Builds {@link PaymentInitiatedEvent} instances representing normal (non-fraud)
 * payment patterns. Uses log-normal amount distributions and Gaussian intraday
 * time distributions for realistic PaySim-style behaviour.
 */
public class TransactionPatternLibrary {

    // Rail selection thresholds (amount in EUR equivalent)
    private static final BigDecimal SEPA_INSTANT_MAX  = BigDecimal.valueOf(100_000);
    private static final BigDecimal CHAPS_MIN         = BigDecimal.valueOf(1_000_000);
    private static final BigDecimal SWIFT_GPI_MIN     = BigDecimal.valueOf(50_000);

    // Intraday peaks: 09:00 (σ=1h) and 15:00 (σ=1.5h), weights 0.6/0.4
    private static final int PEAK_HOUR_1 = 9;
    private static final int PEAK_HOUR_2 = 15;

    private final AgentRegistry agents;
    private final Random rng;
    private final Instant simulationStart;

    public TransactionPatternLibrary(AgentRegistry agents, Random rng, Instant simulationStart) {
        this.agents = agents;
        this.rng = rng;
        this.simulationStart = simulationStart;
    }

    public PaymentInitiatedEvent buildNormal(int dayOffset) {
        AgentRegistry.Agent debtor = agents.random(rng);
        AgentRegistry.Agent creditor;
        do { creditor = agents.random(rng); } while (creditor.id() == debtor.id());

        BigDecimal amount = logNormalAmount(debtor.avgTransaction(), debtor.stdTransaction());
        String currency = currencyForCountry(debtor.country());
        String rail = selectRail(amount, debtor.country(), creditor.country(), currency);
        Instant ts = intradayTimestamp(dayOffset);

        return buildEvent(debtor, creditor, amount, currency, rail, ts, false);
    }

    public PaymentInitiatedEvent buildEvent(AgentRegistry.Agent debtor, AgentRegistry.Agent creditor,
                                            BigDecimal amount, String currency, String rail,
                                            Instant ts, boolean forced) {
        String paymentId = UUID.randomUUID().toString();
        String correlationId = UUID.randomUUID().toString();
        return new PaymentInitiatedEvent(
                paymentId, correlationId,
                "SIM-" + paymentId.substring(0, 8),
                "E2E-" + paymentId.substring(0, 8),
                UUID.randomUUID().toString(),
                debtor.iban(), creditor.iban(),
                debtor.name(), creditor.name(),
                debtor.bic(), creditor.bic(),
                amount, currency,
                debtor.country(), creditor.country(),
                rail, ts, "simulator"
        );
    }

    /** Log-normal amount: exp(μ + σ*N(0,1)), clamped to [0.01, 999_999_999]. */
    public BigDecimal logNormalAmount(double mu, double sigma) {
        double sample = Math.exp(mu + sigma * rng.nextGaussian());
        sample = Math.max(0.01, Math.min(999_999_999.0, sample));
        return BigDecimal.valueOf(Math.round(sample * 100.0) / 100.0);
    }

    /** Gaussian mixture intraday timestamp. */
    public Instant intradayTimestamp(int dayOffset) {
        int peakHour = rng.nextDouble() < 0.6 ? PEAK_HOUR_1 : PEAK_HOUR_2;
        double sigma = (peakHour == PEAK_HOUR_1) ? 3600 : 5400;
        long secondsFromMidnight = (long) (peakHour * 3600 + rng.nextGaussian() * sigma);
        secondsFromMidnight = Math.max(0, Math.min(86399, secondsFromMidnight));

        return simulationStart
                .plus(dayOffset, ChronoUnit.DAYS)
                .atZone(ZoneOffset.UTC)
                .toLocalDate()
                .atStartOfDay(ZoneOffset.UTC)
                .toInstant()
                .plusSeconds(secondsFromMidnight);
    }

    /** Select payment rail based on amount and corridor. */
    public String selectRail(BigDecimal amount, String debtorCountry, String creditorCountry,
                             String currency) {
        boolean isSepaCountry = isSepa(debtorCountry) && isSepa(creditorCountry);
        boolean isGbpDomestic = "GB".equals(debtorCountry) && "GB".equals(creditorCountry);
        boolean isUsdDomestic = "US".equals(debtorCountry) && "US".equals(creditorCountry);

        if (isGbpDomestic) {
            return amount.compareTo(CHAPS_MIN) >= 0 ? "CHAPS" : "FASTER_PAYMENTS";
        }
        if (isUsdDomestic) {
            return amount.compareTo(CHAPS_MIN) >= 0 ? "FEDWIRE" : "FEDACH";
        }
        if (isSepaCountry) {
            return amount.compareTo(SEPA_INSTANT_MAX) <= 0 ? "SEPA_INSTANT" : "SEPA_CREDIT_TRANSFER";
        }
        // Cross-border
        return amount.compareTo(SWIFT_GPI_MIN) >= 0 ? "SWIFT_GPI" : "SWIFT_MT103";
    }

    private static String currencyForCountry(String country) {
        return switch (country) {
            case "GB" -> "GBP";
            case "US", "AU", "CA", "HK", "SG" -> "USD";
            case "JP" -> "JPY";
            case "CH" -> "CHF";
            case "RU" -> "RUB";
            default  -> "EUR";
        };
    }

    private static boolean isSepa(String country) {
        return switch (country) {
            case "DE","FR","NL","ES","IT","AT","BE","SE","FI","PL","PT","IE","LU","EE","LV","LT",
                 "SK","SI","CY","MT","GR","HR","DK","BG","RO","HU","CZ","IS","NO","LI","CH" -> true;
            default -> false;
        };
    }
}
