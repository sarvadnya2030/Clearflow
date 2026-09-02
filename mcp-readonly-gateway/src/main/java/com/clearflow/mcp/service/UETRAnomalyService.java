package com.clearflow.mcp.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Detects UETR velocity anomalies: payments exceeding statistical thresholds.
 *
 * Uses a simple sliding-window z-score on per-debtor payment counts from ES.
 * No ML library needed — pure stats over ES aggregation results.
 *
 * Algorithm:
 *   1. Query ES clearflow-* for the past windowMinutes, aggregate by correlationId
 *      (used as debtor proxy; falls back gracefully if field is missing).
 *   2. Compute mean and stddev of per-debtor counts.
 *   3. Flag any debtor whose count > mean + 2*stddev as MEDIUM,
 *      > mean + 3*stddev as HIGH. Below threshold is LOW (not flagged).
 *   4. Return top 20 anomalies sorted by z-score desc.
 */
@Service
public class UETRAnomalyService {

    private static final Logger log = LoggerFactory.getLogger(UETRAnomalyService.class);

    /** Returned when anomaly detection completes (or gracefully degrades). */
    public record AnomalyReport(
            List<VelocityAnomaly> anomalies,
            int scanned,
            Instant windowStart
    ) {}

    /** A single debtor whose payment velocity exceeds statistical thresholds. */
    public record VelocityAnomaly(
            String debtorRef,
            int count,
            double zScore,
            String severity,      // HIGH | MEDIUM | LOW
            Instant detectedAt
    ) {}

    private final String esUrl;
    private final ObjectMapper mapper;
    private final HttpClient http;

    public UETRAnomalyService(
            @Value("${clearflow.elasticsearch.url:http://localhost:9200}") String esUrl,
            ObjectMapper mapper) {
        this.esUrl  = esUrl;
        this.mapper = mapper;
        this.http   = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .build();
    }

    /**
     * Detect velocity anomalies across debtors in the last {@code windowMinutes} minutes.
     *
     * @param windowMinutes sliding window size, e.g. 60
     * @return AnomalyReport — never null; returns empty report on ES failure
     */
    public AnomalyReport detect(int windowMinutes) {
        int window = windowMinutes > 0 ? windowMinutes : 60;
        Instant windowStart = Instant.now().minus(Duration.ofMinutes(window));

        try {
            Map<String, Long> countsByDebtor = fetchDebtorCounts(window);
            if (countsByDebtor.isEmpty()) {
                return new AnomalyReport(List.of(), 0, windowStart);
            }

            int scanned = countsByDebtor.size();
            List<Long> counts = new ArrayList<>(countsByDebtor.values());

            double mean   = computeMean(counts);
            double stddev = computeStddev(counts, mean);

            List<VelocityAnomaly> anomalies = new ArrayList<>();
            Instant now = Instant.now();

            for (Map.Entry<String, Long> entry : countsByDebtor.entrySet()) {
                double z = (stddev > 0.0) ? (entry.getValue() - mean) / stddev : 0.0;

                if (z > 2.0) {
                    String severity = z > 3.0 ? "HIGH" : "MEDIUM";
                    anomalies.add(new VelocityAnomaly(
                            entry.getKey(),
                            entry.getValue().intValue(),
                            Math.round(z * 1000.0) / 1000.0,
                            severity,
                            now
                    ));
                }
            }

            // Sort by z-score descending, cap at 20
            anomalies.sort(Comparator.comparingDouble(VelocityAnomaly::zScore).reversed());
            List<VelocityAnomaly> top20 = anomalies.size() > 20
                    ? anomalies.subList(0, 20)
                    : anomalies;

            log.info("UETR anomaly scan: window={}m scanned={} anomalies={}", window, scanned, top20.size());
            return new AnomalyReport(top20, scanned, windowStart);

        } catch (Exception e) {
            log.warn("UETRAnomalyService.detect failed, returning empty report: {}", e.getMessage());
            return new AnomalyReport(List.of(), 0, windowStart);
        }
    }

    // ── ES query ─────────────────────────────────────────────────────────────

    /**
     * Query ES for payment events in the last {@code windowMinutes} minutes,
     * grouped by correlationId (UETR/debtor proxy). Returns debtor → count map.
     */
    private Map<String, Long> fetchDebtorCounts(int windowMinutes) {
        // Try correlationId first (UETR-like field), fall back to debtorIban if needed.
        // We run one query using correlationId; ES keyword field required for terms agg.
        String query = buildVelocityAggQuery(windowMinutes, "correlationId");
        Map<String, Long> result = executeTermsAgg(query);

        if (result.isEmpty()) {
            // Retry with debtorIban — may be populated in different event types
            query  = buildVelocityAggQuery(windowMinutes, "debtorIban");
            result = executeTermsAgg(query);
        }
        return result;
    }

    private String buildVelocityAggQuery(int windowMinutes, String keywordField) {
        return """
                {
                  "query": {
                    "bool": {
                      "filter": [
                        { "range": { "@timestamp": { "gte": "now-%dm" } } },
                        { "exists": { "field": "%s" } }
                      ]
                    }
                  },
                  "size": 0,
                  "aggs": {
                    "by_debtor": {
                      "terms": {
                        "field": "%s",
                        "size": 500,
                        "order": { "_count": "desc" }
                      }
                    }
                  }
                }
                """.formatted(windowMinutes, keywordField, keywordField);
    }

    private Map<String, Long> executeTermsAgg(String queryBody) {
        try {
            String url = esUrl + "/clearflow-*/_search";
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .header("Content-Type", "application/json")
                    .timeout(Duration.ofSeconds(10))
                    .POST(HttpRequest.BodyPublishers.ofString(queryBody))
                    .build();

            HttpResponse<String> response = http.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() != 200) {
                log.warn("ES agg returned status {}", response.statusCode());
                return Map.of();
            }

            JsonNode root    = mapper.readTree(response.body());
            JsonNode buckets = root.path("aggregations").path("by_debtor").path("buckets");
            if (!buckets.isArray() || buckets.isEmpty()) {
                return Map.of();
            }

            Map<String, Long> counts = new LinkedHashMap<>();
            buckets.forEach(b -> counts.put(
                    b.path("key").asText("unknown"),
                    b.path("doc_count").asLong(0L)
            ));
            return counts;

        } catch (Exception e) {
            log.warn("executeTermsAgg failed: {}", e.getMessage());
            return Map.of();
        }
    }

    // ── Statistics ────────────────────────────────────────────────────────────

    private double computeMean(List<Long> values) {
        if (values.isEmpty()) return 0.0;
        long sum = 0L;
        for (long v : values) sum += v;
        return (double) sum / values.size();
    }

    private double computeStddev(List<Long> values, double mean) {
        if (values.size() < 2) return 0.0;
        double sumSq = 0.0;
        for (long v : values) {
            double diff = v - mean;
            sumSq += diff * diff;
        }
        return Math.sqrt(sumSq / values.size());
    }
}
