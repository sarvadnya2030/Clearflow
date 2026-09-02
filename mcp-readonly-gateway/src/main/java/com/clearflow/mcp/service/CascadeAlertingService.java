package com.clearflow.mcp.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Phase 4 feature: Multi-channel alerting for cascade failures.
 * Integrates with Slack, PagerDuty, and email for incident notification.
 */
@Service
public class CascadeAlertingService {

    private static final Logger log = LoggerFactory.getLogger(CascadeAlertingService.class);

    private final HttpClient httpClient;
    private final Map<String, Long> alertCooldown = new ConcurrentHashMap<>();

    @Value("${alerts.slack.webhook-url:}")
    private String slackWebhookUrl;

    @Value("${alerts.pagerduty.integration-key:}")
    private String pagerdutyIntegrationKey;

    @Value("${alerts.email.enabled:false}")
    private boolean emailAlertsEnabled;

    private static final long COOLDOWN_MS = 60000;  // Don't spam same alert twice in 1 min

    public CascadeAlertingService() {
        this.httpClient = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .build();
    }

    /**
     * Send cascade alert to all configured channels.
     */
    public void alertCascadeDetected(CascadeFailureDetector.CascadePattern cascade) {
        String alertId = cascade.rootCauseService() + "_" + cascade.cascadeType();

        // Rate limit: don't alert for same cascade more than once per minute
        if (!shouldAlert(alertId)) {
            log.debug("Alert suppressed by cooldown for {}", alertId);
            return;
        }

        try {
            if (!slackWebhookUrl.isEmpty()) {
                alertSlack(cascade);
            }

            if (!pagerdutyIntegrationKey.isEmpty() && cascade.severity().equals("CRITICAL")) {
                alertPagerDuty(cascade);
            }

            if (emailAlertsEnabled) {
                alertEmail(cascade);
            }

            recordAlert(alertId);
        } catch (Exception ex) {
            log.error("Failed to send cascade alert", ex);
        }
    }

    /**
     * Send alert to Slack webhook.
     */
    private void alertSlack(CascadeFailureDetector.CascadePattern cascade) {
        try {
            String emoji = cascade.severity().equals("CRITICAL") ? "🔴" : "🟠";
            String color = cascade.severity().equals("CRITICAL") ? "#FF0000" : "#FF9900";

            String payload = String.format("""
                {
                  "blocks": [
                    {
                      "type": "header",
                      "text": {"type": "plain_text", "text": "%s CASCADE FAILURE DETECTED", "emoji": true}
                    },
                    {
                      "type": "section",
                      "fields": [
                        {"type": "mrkdwn", "text": "*Root Cause:*\\n%s"},
                        {"type": "mrkdwn", "text": "*Type:*\\n%s"},
                        {"type": "mrkdwn", "text": "*Severity:*\\n%s"},
                        {"type": "mrkdwn", "text": "*Affected Services:*\\n%d"}
                      ]
                    },
                    {
                      "type": "section",
                      "text": {"type": "mrkdwn", "text": "*Propagation Chain:*\\n```%s```"}
                    },
                    {
                      "type": "section",
                      "text": {"type": "mrkdwn", "text": "*Speed:* %.1f ms/stage | *ID:* `%s`"}
                    }
                  ]
                }
                """,
                emoji,
                cascade.rootCauseService(),
                cascade.cascadeType(),
                cascade.severity(),
                cascade.propagationChain().size(),
                formatChain(cascade),
                cascade.propagationSpeed(),
                cascade.id()
            );

            HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(slackWebhookUrl))
                .timeout(Duration.ofSeconds(5))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(payload))
                .build();

            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() == 200) {
                log.info("Slack alert sent for cascade {}", cascade.id());
            } else {
                log.warn("Slack alert failed with status {}", response.statusCode());
            }
        } catch (Exception ex) {
            log.error("Failed to send Slack alert", ex);
        }
    }

    /**
     * Send CRITICAL alert to PagerDuty.
     */
    private void alertPagerDuty(CascadeFailureDetector.CascadePattern cascade) {
        try {
            String payload = String.format("""
                {
                  "routing_key": "%s",
                  "event_action": "trigger",
                  "dedup_key": "%s",
                  "payload": {
                    "summary": "CASCADE: %s (%s) - %d services affected",
                    "severity": "critical",
                    "source": "ClearFlow-MCP",
                    "custom_details": {
                      "root_cause": "%s",
                      "cascade_type": "%s",
                      "propagation_speed_ms": %.1f,
                      "affected_services": %d,
                      "cascade_id": "%s"
                    }
                  }
                }
                """,
                pagerdutyIntegrationKey,
                cascade.id(),
                cascade.rootCauseService(),
                cascade.cascadeType(),
                cascade.propagationChain().size(),
                cascade.rootCauseService(),
                cascade.cascadeType(),
                cascade.propagationSpeed(),
                cascade.propagationChain().size(),
                cascade.id()
            );

            HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://events.pagerduty.com/v2/enqueue"))
                .timeout(Duration.ofSeconds(5))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(payload))
                .build();

            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() == 202) {
                log.info("PagerDuty alert sent for cascade {}", cascade.id());
            } else {
                log.warn("PagerDuty alert failed with status {}", response.statusCode());
            }
        } catch (Exception ex) {
            log.error("Failed to send PagerDuty alert", ex);
        }
    }

    /**
     * Send email alert (placeholder).
     */
    private void alertEmail(CascadeFailureDetector.CascadePattern cascade) {
        try {
            // Future: integrate with SMTP/SES
            log.info("Email alert would be sent for cascade {}", cascade.id());
        } catch (Exception ex) {
            log.error("Failed to send email alert", ex);
        }
    }

    private String formatChain(CascadeFailureDetector.CascadePattern cascade) {
        return cascade.propagationChain().stream()
            .map(e -> String.format("%s[%d] @ %s", e.service(), e.stageNumber(), e.timestamp()))
            .reduce((a, b) -> a + " → " + b)
            .orElse("(no chain)");
    }

    private boolean shouldAlert(String alertId) {
        long lastAlert = alertCooldown.getOrDefault(alertId, 0L);
        long now = System.currentTimeMillis();
        return (now - lastAlert) > COOLDOWN_MS;
    }

    private void recordAlert(String alertId) {
        alertCooldown.put(alertId, System.currentTimeMillis());
    }
}
