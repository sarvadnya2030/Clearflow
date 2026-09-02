package com.clearflow.gateway.simulator;

import com.clearflow.common.domain.PaymentInitiatedEvent;
import com.clearflow.gateway.messaging.ActiveMQPublisher;
import com.clearflow.gateway.messaging.KafkaEventPublisher;
import com.clearflow.gateway.messaging.SolacePublisher;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.UUID;

/**
 * Activated via {@code --spring.profiles.active=simulator}.
 * Generates 100k+ synthetic payments using PaySimEngine and publishes
 * them in configurable batches to all three message brokers (Kafka,
 * ActiveMQ, Solace).
 *
 * Run with:
 *   java -jar gateway.jar --spring.profiles.active=simulator
 *   CLEARFLOW_SIMULATOR_TOTALTRANSACTIONS=100000 java -jar gateway.jar --spring.profiles.active=simulator
 */
@Component
@Profile("simulator")
public class SimulatorCommandLineRunner implements CommandLineRunner {

    private static final Logger log = LoggerFactory.getLogger(SimulatorCommandLineRunner.class);

    private final PaySimEngine engine;
    private final SimulatorConfig config;
    private final KafkaEventPublisher kafkaPublisher;
    private final ActiveMQPublisher activeMQPublisher;
    private final SolacePublisher solacePublisher;

    public SimulatorCommandLineRunner(PaySimEngine engine,
                                      SimulatorConfig config,
                                      KafkaEventPublisher kafkaPublisher,
                                      ActiveMQPublisher activeMQPublisher,
                                      SolacePublisher solacePublisher) {
        this.engine = engine;
        this.config = config;
        this.kafkaPublisher = kafkaPublisher;
        this.activeMQPublisher = activeMQPublisher;
        this.solacePublisher = solacePublisher;
    }

    @Override
    public void run(String... args) throws Exception {
        log.info("=== ClearFlow PaySim Simulator starting ===");
        List<PaymentInitiatedEvent> events = engine.generate();

        int total = events.size();
        int batchSize = config.getBatchSize();
        int published = 0;
        int errors = 0;

        log.info("Publishing {} events in batches of {} (pause={}ms)",
                total, batchSize, config.getBatchPauseMs());

        for (int i = 0; i < total; i += batchSize) {
            int end = Math.min(i + batchSize, total);
            List<PaymentInitiatedEvent> batch = events.subList(i, end);

            for (PaymentInitiatedEvent event : batch) {
                try {
                    String traceId = "00-" + event.paymentId().replace("-", "") + "-0000000000000000-01";
                    kafkaPublisher.publish(event, traceId, "");
                    activeMQPublisher.publish(event, "simulator");
                    solacePublisher.publish(event);
                    published++;
                } catch (Exception ex) {
                    errors++;
                    log.warn("Failed to publish paymentId={}: {}", event.paymentId(), ex.getMessage());
                }
            }

            if (config.getBatchPauseMs() > 0 && end < total) {
                Thread.sleep(config.getBatchPauseMs());
            }

            if ((i / batchSize) % 10 == 0) {
                log.info("Progress: {}/{} published, {} errors", published, total, errors);
            }
        }

        log.info("=== PaySim Simulator complete: published={} errors={} total={} ===",
                published, errors, total);
    }
}
