package com.clearflow.gateway.simulator;

import com.clearflow.common.domain.PaymentInitiatedEvent;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;

/**
 * PaySim-inspired engine that generates a synthetic payment dataset.
 *
 * Architecture:
 *   - 2,000 agents across 30+ countries
 *   - 30-day simulation window
 *   - Log-normal amount distributions per agent type
 *   - Gaussian intraday time distribution (dual peaks: 09:00, 15:00)
 *   - Configurable fraud + AML injection rates
 */
@Component
public class PaySimEngine {

    private static final Logger log = LoggerFactory.getLogger(PaySimEngine.class);

    private final SimulatorConfig config;

    public PaySimEngine(SimulatorConfig config) {
        this.config = config;
    }

    /**
     * Generate the full transaction dataset.
     * @return list of {@link PaymentInitiatedEvent} ready to publish
     */
    public List<PaymentInitiatedEvent> generate() {
        long seed = config.getRandomSeed() != 0 ? config.getRandomSeed() : System.currentTimeMillis();
        Random rng = new Random(seed);
        log.info("PaySimEngine starting: agents={} days={} target={} fraudRate={} amlRate={} seed={}",
                config.getAgentCount(), config.getSimulationDays(), config.getTotalTransactions(),
                config.getFraudRate(), config.getAmlRate(), seed);

        AgentRegistry agents = new AgentRegistry(config.getAgentCount(), rng);
        Instant simStart = Instant.now().truncatedTo(ChronoUnit.DAYS)
                .minus(config.getSimulationDays(), ChronoUnit.DAYS);

        TransactionPatternLibrary lib = new TransactionPatternLibrary(agents, rng, simStart);
        FraudPatternInjector fraudInjector = new FraudPatternInjector(agents, lib, rng);
        AMLPatternInjector amlInjector = new AMLPatternInjector(agents, lib, rng);

        int total = config.getTotalTransactions();
        int fraudBudget = (int) (total * config.getFraudRate());
        int amlBudget = (int) (total * config.getAmlRate());
        int normalBudget = total - fraudBudget - amlBudget;

        List<PaymentInitiatedEvent> events = new ArrayList<>(total + 100);

        // Normal transactions distributed across days
        int txPerDay = normalBudget / config.getSimulationDays();
        for (int day = 0; day < config.getSimulationDays(); day++) {
            for (int t = 0; t < txPerDay; t++) {
                events.add(lib.buildNormal(day));
            }
        }
        // Remainder
        for (int i = events.size(); i < normalBudget; i++) {
            events.add(lib.buildNormal(rng.nextInt(config.getSimulationDays())));
        }

        // Fraud events
        int injected = 0;
        while (injected < fraudBudget) {
            int day = rng.nextInt(config.getSimulationDays());
            List<PaymentInitiatedEvent> batch = fraudInjector.inject(day);
            events.addAll(batch);
            injected += batch.size();
        }

        // AML events
        injected = 0;
        while (injected < amlBudget) {
            int day = rng.nextInt(config.getSimulationDays());
            List<PaymentInitiatedEvent> batch = amlInjector.inject(day);
            events.addAll(batch);
            injected += batch.size();
        }

        log.info("PaySimEngine generated {} events (normal={} fraud≈{} aml≈{})",
                events.size(), normalBudget, fraudBudget, amlBudget);
        return events;
    }
}
