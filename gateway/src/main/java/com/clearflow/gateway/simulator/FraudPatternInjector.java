package com.clearflow.gateway.simulator;

import com.clearflow.common.domain.PaymentInitiatedEvent;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;
import java.util.UUID;

/**
 * Injects 6 fraud patterns inspired by the PaySim research paper.
 *
 * Patterns:
 *  1. ACCOUNT_TAKEOVER    — single account suddenly sends large amount to new counterpart
 *  2. VELOCITY_BURST      — rapid repeated payments from same debtor IBAN
 *  3. ROUND_TRIP          — A→B→C→A same currency cycle
 *  4. MULE_NETWORK        — fan-out: one sender → 5 different recipients
 *  5. IMPOSSIBLE_GEOGRAPHY— two payments from same account, distant countries, <1h apart
 *  6. EMBARGOED_TRANSIT   — payment routed through/to OFAC embargoed country
 */
public class FraudPatternInjector {

    private static final String[] EMBARGOED = {"IR", "KP", "CU", "SY"};

    private final AgentRegistry agents;
    private final TransactionPatternLibrary lib;
    private final Random rng;

    public FraudPatternInjector(AgentRegistry agents, TransactionPatternLibrary lib, Random rng) {
        this.agents = agents;
        this.lib = lib;
        this.rng = rng;
    }

    /** Generate a batch of fraud events for a given day. Returns 1–6 events. */
    public List<PaymentInitiatedEvent> inject(int dayOffset) {
        int pattern = rng.nextInt(6);
        return switch (pattern) {
            case 0 -> accountTakeover(dayOffset);
            case 1 -> velocityBurst(dayOffset);
            case 2 -> roundTrip(dayOffset);
            case 3 -> muleNetwork(dayOffset);
            case 4 -> impossibleGeography(dayOffset);
            default -> embargoedTransit(dayOffset);
        };
    }

    private List<PaymentInitiatedEvent> accountTakeover(int day) {
        AgentRegistry.Agent victim = agents.random(rng);
        AgentRegistry.Agent attacker = agents.random(rng);
        // Large, off-hours, first-time pair
        Instant ts = offHours(day);
        BigDecimal amount = BigDecimal.valueOf(50_000 + rng.nextInt(200_000));
        return List.of(lib.buildEvent(victim, attacker, amount, "EUR", "SEPA_INSTANT", ts, true));
    }

    private List<PaymentInitiatedEvent> velocityBurst(int day) {
        AgentRegistry.Agent debtor = agents.random(rng);
        AgentRegistry.Agent creditor = agents.random(rng);
        Instant base = lib.intradayTimestamp(day);
        List<PaymentInitiatedEvent> events = new ArrayList<>();
        for (int i = 0; i < 5; i++) {
            Instant ts = base.plusSeconds(i * 45L); // 45s apart
            BigDecimal amount = BigDecimal.valueOf(9_800 + rng.nextInt(400)); // structuring band
            events.add(lib.buildEvent(debtor, creditor, amount, "EUR", "SEPA_INSTANT", ts, true));
        }
        return events;
    }

    private List<PaymentInitiatedEvent> roundTrip(int day) {
        AgentRegistry.Agent a = agents.random(rng);
        AgentRegistry.Agent b = agents.random(rng);
        AgentRegistry.Agent c = agents.random(rng);
        BigDecimal seed = BigDecimal.valueOf(50_000 + rng.nextInt(100_000));
        BigDecimal leg2 = seed.multiply(BigDecimal.valueOf(0.995));
        BigDecimal leg3 = leg2.multiply(BigDecimal.valueOf(0.995));
        Instant t1 = lib.intradayTimestamp(day);
        Instant t2 = t1.plusSeconds(3600);
        Instant t3 = t2.plusSeconds(3600);
        return List.of(
                lib.buildEvent(a, b, seed, "EUR", "SEPA_CREDIT_TRANSFER", t1, true),
                lib.buildEvent(b, c, leg2, "EUR", "SEPA_CREDIT_TRANSFER", t2, true),
                lib.buildEvent(c, a, leg3, "EUR", "SEPA_CREDIT_TRANSFER", t3, true)
        );
    }

    private List<PaymentInitiatedEvent> muleNetwork(int day) {
        AgentRegistry.Agent source = agents.random(rng);
        BigDecimal total = BigDecimal.valueOf(80_000 + rng.nextInt(120_000));
        List<PaymentInitiatedEvent> events = new ArrayList<>();
        for (int i = 0; i < 5; i++) {
            AgentRegistry.Agent mule = agents.random(rng);
            BigDecimal slice = total.divide(BigDecimal.valueOf(5), 2, java.math.RoundingMode.DOWN);
            Instant ts = lib.intradayTimestamp(day).plusSeconds(i * 180L);
            events.add(lib.buildEvent(source, mule, slice, "EUR", "SEPA_INSTANT", ts, true));
        }
        return events;
    }

    private List<PaymentInitiatedEvent> impossibleGeography(int day) {
        // UK agent makes a payment, then "same account" in Singapore 30min later
        AgentRegistry.Agent gbAgent = safeAgentFromCountry("GB", agents.random(rng));
        AgentRegistry.Agent sgAgent = safeAgentFromCountry("SG", agents.random(rng));
        AgentRegistry.Agent counterpart = agents.random(rng);
        Instant t1 = lib.intradayTimestamp(day);
        Instant t2 = t1.plusSeconds(1800); // 30 min later
        // Reuse same IBAN to simulate impossible geography
        return List.of(
                lib.buildEvent(gbAgent, counterpart, BigDecimal.valueOf(15_000), "GBP", "FASTER_PAYMENTS", t1, true),
                lib.buildEvent(sgAgent, counterpart, BigDecimal.valueOf(12_000), "USD", "SWIFT_GPI", t2, true)
        );
    }

    private List<PaymentInitiatedEvent> embargoedTransit(int day) {
        String embargoed = EMBARGOED[rng.nextInt(EMBARGOED.length)];
        AgentRegistry.Agent debtor = agents.random(rng);
        // Create a synthetic embargoed creditor
        String fakeIban = IbanGeneratorUtil.generate(embargoed, rng);
        String fakeBic = embargoed + "BNKXXX";
        AgentRegistry.Agent creditor = new AgentRegistry.Agent(
                99999, "Embargoed Entity (" + embargoed + ")",
                embargoed, fakeIban, fakeBic,
                AgentRegistry.AgentType.HIGH_RISK, 13.0, 1.5);

        BigDecimal amount = BigDecimal.valueOf(500_000 + rng.nextInt(2_000_000));
        Instant ts = lib.intradayTimestamp(day);
        return List.of(lib.buildEvent(debtor, creditor, amount, "USD", "SWIFT_GPI", ts, true));
    }

    private AgentRegistry.Agent safeAgentFromCountry(String country, AgentRegistry.Agent fallback) {
        var list = agents.byCountry(country);
        return list.isEmpty() ? fallback : list.get(rng.nextInt(list.size()));
    }

    private Instant offHours(int dayOffset) {
        return java.time.LocalDate.now(ZoneOffset.UTC)
                .plusDays(dayOffset)
                .atTime(3, rng.nextInt(59))
                .toInstant(ZoneOffset.UTC);
    }
}
