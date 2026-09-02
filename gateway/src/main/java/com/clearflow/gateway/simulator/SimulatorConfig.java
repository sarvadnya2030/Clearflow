package com.clearflow.gateway.simulator;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;

/**
 * Configuration properties for the PaySim-inspired transaction simulator.
 * Bind via prefix {@code clearflow.simulator} in application.yml / env.
 */
@Configuration
@ConfigurationProperties(prefix = "clearflow.simulator")
public class SimulatorConfig {

    /** Total synthetic agents (payer/payee profiles) to generate. */
    private int agentCount = 5000;

    /** Number of calendar days to simulate. */
    private int simulationDays = 90;

    /** Target total transactions across the full simulation window. */
    private int totalTransactions = 1_00_000;

    /** Fraud injection rate (0.0–1.0). */
    private double fraudRate = 0.02;

    /** AML injection rate (0.0–1.0). */
    private double amlRate = 0.005;

    /** Seed for reproducible runs (0 = random). */
    private long randomSeed = 0L;

    /** Batch size for Kafka publishing bursts. */
    private int batchSize = 1000;

    /** Pause (ms) between batches to avoid overwhelming brokers. */
    private long batchPauseMs = 200;

    public int getAgentCount() { return agentCount; }
    public void setAgentCount(int agentCount) { this.agentCount = agentCount; }

    public int getSimulationDays() { return simulationDays; }
    public void setSimulationDays(int simulationDays) { this.simulationDays = simulationDays; }

    public int getTotalTransactions() { return totalTransactions; }
    public void setTotalTransactions(int totalTransactions) { this.totalTransactions = totalTransactions; }

    public double getFraudRate() { return fraudRate; }
    public void setFraudRate(double fraudRate) { this.fraudRate = fraudRate; }

    public double getAmlRate() { return amlRate; }
    public void setAmlRate(double amlRate) { this.amlRate = amlRate; }

    public long getRandomSeed() { return randomSeed; }
    public void setRandomSeed(long randomSeed) { this.randomSeed = randomSeed; }

    public int getBatchSize() { return batchSize; }
    public void setBatchSize(int batchSize) { this.batchSize = batchSize; }

    public long getBatchPauseMs() { return batchPauseMs; }
    public void setBatchPauseMs(long batchPauseMs) { this.batchPauseMs = batchPauseMs; }
}
