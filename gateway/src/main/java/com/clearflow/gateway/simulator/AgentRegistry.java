package com.clearflow.gateway.simulator;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Random;

/**
 * Generates and holds a population of synthetic payment agents (payers/payees)
 * spanning 30+ countries. Each agent has a home country, IBAN, BIC, and a
 * behavioural profile used by PaySimEngine for amount distribution.
 */
public class AgentRegistry {

    /** Synthetic agent profile. */
    public record Agent(
            int id,
            String name,
            String country,
            String iban,
            String bic,
            AgentType type,
            double avgTransaction,   // mean of log-normal distribution
            double stdTransaction    // sigma of log-normal distribution
    ) {}

    public enum AgentType { RETAIL, CORPORATE, FINANCIAL_INSTITUTION, HIGH_RISK }

    // Country weights: approximate realistic transaction distribution
    private static final String[][] COUNTRY_POOL = {
            {"DE", "DEUTDEFFXXX"}, {"DE", "COBADEFFXXX"}, {"DE", "DRESDEFF"},
            {"GB", "BARCGB22XXX"}, {"GB", "HBUKGB4BXXX"}, {"GB", "NWBKGB2LXXX"},
            {"FR", "BNPAFRPPXXX"}, {"FR", "SOGEFRPPXXX"}, {"FR", "CRLYFRPPXXX"},
            {"NL", "INGBNL2AXXX"}, {"NL", "ABNANL2AXXX"}, {"NL", "RABONL2UXXX"},
            {"ES", "CAIXESBBXXX"}, {"ES", "BBVAESMMXXX"}, {"ES", "BSCHESMMXXX"},
            {"IT", "UNCRITMM"},    {"IT", "BNLIITRR"},    {"IT", "PASCITMM"},
            {"AT", "BKAUATWWXXX"}, {"BE", "BBRUBEBB"},
            {"SE", "NDEASESSXXX"}, {"FI", "NDEAFIHHXXX"}, {"PL", "BPKOPLPW"},
            {"US", "CHASUS33XXX"}, {"US", "BOFAUS3NXXX"}, {"US", "WFBIUS6SXXX"},
            {"AU", "ANZBAU3MXXX"}, {"CA", "ROYCCAT2XXX"}, {"HK", "HSBCHKHHHKH"},
            {"JP", "MHCBJPJTXXX"}, {"SG", "DBSSSGSGXXX"}, {"ZA", "SBZAZAJJXXX"},
            {"AE", "NBADAEAAXXX"}, {"BR", "ITAUBRSPXXX"}, {"CH", "UBSWCHZHXXX"},
            // High-risk / FATF countries (lower weight but needed for fraud patterns)
            {"RU", "SABRRUMM"},    {"NG", "FIDTNGLA"},    {"BO", "BNBOBO2BXXX"},
            {"MM", "MABCMMMY"},    {"CU", "BFICCUHA"},    {"SY", "BSYBSYDA"},
            {"IR", "MELRIR21"},    {"KP", "KORYUS33"}
    };

    private final List<Agent> agents;

    public AgentRegistry(int count, Random rng) {
        agents = new ArrayList<>(count);
        for (int i = 0; i < count; i++) {
            String[] pool = COUNTRY_POOL[rng.nextInt(COUNTRY_POOL.length)];
            String country = pool[0];
            String bic = pool[1];
            String iban = IbanGeneratorUtil.generate(country, rng);

            // Assign type and transaction profile
            double typeRoll = rng.nextDouble();
            AgentType type;
            double avg, std;
            if (typeRoll < 0.60) {
                type = AgentType.RETAIL; avg = 7.5; std = 1.2;      // €1K–€20K
            } else if (typeRoll < 0.85) {
                type = AgentType.CORPORATE; avg = 11.5; std = 1.5;  // €100K–€2M
            } else if (typeRoll < 0.95) {
                type = AgentType.FINANCIAL_INSTITUTION; avg = 14.0; std = 1.0; // €1M–€50M
            } else {
                type = AgentType.HIGH_RISK; avg = 8.5; std = 1.8;   // varied
            }

            String name = type.name().toLowerCase().replace('_', ' ')
                    + " agent-" + i + " (" + country + ")";
            agents.add(new Agent(i, name, country, iban, bic, type, avg, std));
        }
    }

    public Agent get(int index) { return agents.get(index % agents.size()); }

    public Agent random(Random rng) { return agents.get(rng.nextInt(agents.size())); }

    public int size() { return agents.size(); }

    /** Return agents from a specific country. */
    public List<Agent> byCountry(String country) {
        return agents.stream().filter(a -> a.country().equals(country)).toList();
    }

    public List<Agent> all() { return Collections.unmodifiableList(agents); }
}
