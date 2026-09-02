package com.clearflow.gateway.simulator;

import com.clearflow.common.domain.PaymentInitiatedEvent;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;

/**
 * Injects 4 AML patterns designed to trigger the FuzzyScreeningEngine and PEP checks.
 *
 * Patterns:
 *  1. SDN_NAME_MATCH      — debtor name matches (or near-matches) SDN entry
 *  2. PEP_LINKED          — creditor name matches PEP list (triggers EDD)
 *  3. STRUCTURING         — multiple payments just below €10K threshold (5-payment cycle)
 *  4. FATF_GREY_LIST      — payment corridor to/from FATF grey-list country
 */
public class AMLPatternInjector {

    // Known SDN-adjacent names from sdn_sample.csv (fuzzy variants for test)
    private static final String[] SDN_VARIANTS = {
            "LAZURUS GROUP", "LAZARUS GROOP", "IRGC-QF FRONT",
            "HAMAS EZZEDEEN BRIGADES", "AL QAEDA FOUNDATION",
            "BANK SADERAT IRAN INTL", "RECONNAISSANCE BUREAU KOREA",
            "SINALOA CARTEL LOGISTICS", "WAGENER GROUP SECURITY"
    };

    // PEP-linked names from pep_sample.csv
    private static final String[] PEP_NAMES = {
            "Aleksandr Volkov", "Zhang Wei Minister", "Emeka Nwosu Governor",
            "Nicolas Maduro Trusted", "Ali Khamenei Foundation"
    };

    // FATF grey-list countries
    private static final String[] FATF_GREY = {"BO", "MM", "NG", "PK", "SY", "YE", "ZM"};

    private final AgentRegistry agents;
    private final TransactionPatternLibrary lib;
    private final Random rng;

    public AMLPatternInjector(AgentRegistry agents, TransactionPatternLibrary lib, Random rng) {
        this.agents = agents;
        this.lib = lib;
        this.rng = rng;
    }

    /** Generate AML events for a given day. Returns 1–5 events. */
    public List<PaymentInitiatedEvent> inject(int dayOffset) {
        int pattern = rng.nextInt(4);
        return switch (pattern) {
            case 0 -> sdnNameMatch(dayOffset);
            case 1 -> pepLinked(dayOffset);
            case 2 -> structuring(dayOffset);
            default -> fatfGreyList(dayOffset);
        };
    }

    private List<PaymentInitiatedEvent> sdnNameMatch(int day) {
        AgentRegistry.Agent debtor = agents.random(rng);
        String sdnName = SDN_VARIANTS[rng.nextInt(SDN_VARIANTS.length)];
        // Craft a synthetic "SDN-like" creditor
        AgentRegistry.Agent creditor = new AgentRegistry.Agent(
                88001 + rng.nextInt(100), sdnName, debtor.country(),
                IbanGeneratorUtil.generate(debtor.country(), rng), debtor.bic(),
                AgentRegistry.AgentType.HIGH_RISK, 12.0, 1.5);

        BigDecimal amount = BigDecimal.valueOf(25_000 + rng.nextInt(200_000));
        Instant ts = lib.intradayTimestamp(day);
        return List.of(lib.buildEvent(debtor, creditor, amount, "USD", "SWIFT_GPI", ts, true));
    }

    private List<PaymentInitiatedEvent> pepLinked(int day) {
        String pepName = PEP_NAMES[rng.nextInt(PEP_NAMES.length)];
        AgentRegistry.Agent debtor = agents.random(rng);
        AgentRegistry.Agent creditor = new AgentRegistry.Agent(
                88101 + rng.nextInt(100), pepName, "RU",
                IbanGeneratorUtil.generate("RU", rng), "SABRRUMM",
                AgentRegistry.AgentType.HIGH_RISK, 12.5, 1.2);

        BigDecimal amount = BigDecimal.valueOf(35_000 + rng.nextInt(150_000));
        Instant ts = lib.intradayTimestamp(day);
        return List.of(lib.buildEvent(debtor, creditor, amount, "EUR", "SWIFT_GPI", ts, true));
    }

    private List<PaymentInitiatedEvent> structuring(int day) {
        // 5 payments just under €10K threshold over ~2 hours
        AgentRegistry.Agent debtor = agents.random(rng);
        AgentRegistry.Agent creditor = agents.random(rng);
        List<PaymentInitiatedEvent> events = new ArrayList<>();
        Instant base = lib.intradayTimestamp(day);
        for (int i = 0; i < 5; i++) {
            // Values in €9,750–€9,999
            BigDecimal amount = BigDecimal.valueOf(9_750 + rng.nextInt(250));
            Instant ts = base.plusSeconds(i * 1800L); // 30 min apart
            events.add(lib.buildEvent(debtor, creditor, amount, "EUR", "SEPA_INSTANT", ts, true));
        }
        return events;
    }

    private List<PaymentInitiatedEvent> fatfGreyList(int day) {
        String greyCountry = FATF_GREY[rng.nextInt(FATF_GREY.length)];
        AgentRegistry.Agent debtorEU = agents.random(rng);
        AgentRegistry.Agent creditorGrey = new AgentRegistry.Agent(
                88201 + rng.nextInt(100), "Local Entity (" + greyCountry + ")",
                greyCountry, IbanGeneratorUtil.generate(greyCountry, rng),
                greyCountry + "BNKXXX", AgentRegistry.AgentType.RETAIL, 9.0, 1.5);

        BigDecimal amount = BigDecimal.valueOf(15_000 + rng.nextInt(60_000));
        Instant ts = lib.intradayTimestamp(day);
        return List.of(lib.buildEvent(debtorEU, creditorGrey, amount, "EUR", "SWIFT_MT103", ts, true));
    }
}
