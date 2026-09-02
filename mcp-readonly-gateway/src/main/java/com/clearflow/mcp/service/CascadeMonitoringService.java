package com.clearflow.mcp.service;

import com.clearflow.mcp.controller.CascadeDetectionController;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Background monitoring service that continuously watches for cascade failures.
 * Runs periodic checks, broadcasts SSE alerts, and integrates with multi-channel alerting (Slack, PagerDuty).
 */
@Service
public class CascadeMonitoringService {

    private static final Logger log = LoggerFactory.getLogger(CascadeMonitoringService.class);

    private final CascadeFailureDetector detector;
    private final CascadeDetectionController controller;
    private final CascadeAlertingService alertingService;
    private final Set<String> alertedCascades = ConcurrentHashMap.newKeySet();

    public CascadeMonitoringService(
        CascadeFailureDetector detector,
        CascadeDetectionController controller,
        CascadeAlertingService alertingService) {
        this.detector = detector;
        this.controller = controller;
        this.alertingService = alertingService;
    }

    /**
     * Runs every 10 seconds to detect new cascades.
     * Checks last 5 minutes of logs for cascade patterns.
     */
    @Scheduled(fixedDelay = 10000, initialDelay = 5000)
    public void monitorForCascades() {
        try {
            List<CascadeFailureDetector.CascadePattern> cascades =
                detector.detectActiveCascades(5);

            for (CascadeFailureDetector.CascadePattern cascade : cascades) {
                // Only broadcast if not already alerted
                if (alertedCascades.add(cascade.id())) {
                    log.warn("New cascade detected: {} type={} severity={} services={}",
                        cascade.id(),
                        cascade.cascadeType(),
                        cascade.severity(),
                        cascade.propagationChain().size()
                    );

                    // Broadcast to connected SSE clients
                    controller.broadcastCascadeAlert(cascade);

                    // Send multi-channel alerts (Slack, PagerDuty, email)
                    alertingService.alertCascadeDetected(cascade);

                    // Log alert message
                    String alert = detector.generateAlert(cascade);
                    log.warn("\n{}", alert);
                }
            }

            // Clean up stale cascade alerts (not seen in last 5 minutes)
            cascades.stream()
                .map(CascadeFailureDetector.CascadePattern::id)
                .forEach(alertedCascades::add);

        } catch (Exception ex) {
            log.error("Cascade monitoring error", ex);
        }
    }

    /**
     * Health check for monitoring service.
     */
    public boolean isMonitoring() {
        return true;
    }

    /**
     * Get count of active cascade alerts.
     */
    public int getActiveAlertCount() {
        return alertedCascades.size();
    }
}
