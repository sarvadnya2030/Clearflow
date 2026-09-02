package com.clearflow.mcp.service;

import org.springframework.stereotype.Service;

import java.util.LinkedHashMap;
import java.util.Map;

@Service
public class McpMetricsService {

    private final ElasticsearchLogFetcher logFetcher;

    public McpMetricsService(ElasticsearchLogFetcher logFetcher) {
        this.logFetcher = logFetcher;
    }

    public Map<String, Long> railDistribution(int windowMinutes) {
        return logFetcher.countByField("rail", windowMinutes);
    }

    public Map<String, Long> fraudHistogram(int windowMinutes) {
        return logFetcher.countByField("riskBand", windowMinutes);
    }

    public Map<String, Object> overview(int windowMinutes) {
        Map<String, Long> events = logFetcher.countByEventType(null, windowMinutes);
        long total = events.getOrDefault("PAYMENT_SUBMITTED", 0L);
        long settled = events.getOrDefault("SETTLEMENT_COMPLETE", 0L);
        long fraudBlocked = events.getOrDefault("PAYMENT_BLOCKED", 0L)
                + events.getOrDefault("PAYMENT_BLOCKED_AT_VALIDATION", 0L);
        long amlBlocked = events.getOrDefault("AML_SANCTIONS_HIT", 0L);
        long rejected = events.getOrDefault("PAYMENT_REJECTED", 0L);

        double avgLatency = logFetcher.averageDuration(windowMinutes);

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("paymentsSubmitted", total);
        result.put("settled", settled);
        result.put("fraudFlagged", fraudBlocked);
        result.put("amlBlocked", amlBlocked);
        result.put("rejected", rejected);
        result.put("avgLatencyMs", Math.round(avgLatency));
        result.put("activeRails", railDistribution(windowMinutes).size());
        return result;
    }
}
