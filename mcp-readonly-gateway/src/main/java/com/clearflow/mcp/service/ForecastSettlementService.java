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
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * Forecasts settlement volume for the next N hours using exponential smoothing
 * (Holt-Winters simple ES) on historical hourly settlement counts from Elasticsearch.
 *
 * No external ML library — pure time-series smoothing in Java.
 *
 * Algorithm:
 *   1. Query clearflow-settlement-* for the last 48 hours using a date_histogram (1h).
 *   2. Compute a smoothed series: s[t] = alpha * x[t] + (1-alpha) * s[t-1], alpha=0.3
 *   3. Extrapolate for each future hour i:
 *        predicted = s[last] * (1 + trend * i)
 *      where trend = avg of last 6 hour-over-hour deltas / s[last]
 *   4. 95% CI: predicted ± 1.96 * stddev(residuals)
 *   5. Return hourly forecasts for the next {@code horizonHours}.
 */
@Service
public class ForecastSettlementService {

    private static final Logger log = LoggerFactory.getLogger(ForecastSettlementService.class);

    private static final double ALPHA = 0.3;
    private static final double Z_95  = 1.96;

    /** Top-level result returned to callers. */
    public record ForecastResult(
            List<HourlyForecast> forecasts,
            double confidence,
            String method,
            Instant generatedAt
    ) {}

    /** Prediction for a single future hour. */
    public record HourlyForecast(
            Instant hour,
            double predicted,
            double lower95,
            double upper95
    ) {}

    private final String esUrl;
    private final ObjectMapper mapper;
    private final HttpClient http;

    public ForecastSettlementService(
            @Value("${clearflow.elasticsearch.url:http://localhost:9200}") String esUrl,
            ObjectMapper mapper) {
        this.esUrl  = esUrl;
        this.mapper = mapper;
        this.http   = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .build();
    }

    /**
     * Generate a settlement volume forecast for the next {@code horizonHours} hours.
     *
     * @param horizonHours number of future hours to forecast (1–168; capped at 168)
     * @return ForecastResult — never null; returns empty forecast on ES failure
     */
    public ForecastResult forecast(int horizonHours) {
        int horizon = Math.max(1, Math.min(horizonHours, 168));
        Instant now = Instant.now().truncatedTo(ChronoUnit.HOURS);

        try {
            List<Double> historicalCounts = fetchHourlyCounts(48);

            if (historicalCounts.isEmpty()) {
                log.warn("No historical settlement data found; returning zero forecast");
                return buildZeroForecast(horizon, now);
            }

            // Step 1: Exponential smoothing
            List<Double> smoothed = exponentialSmooth(historicalCounts, ALPHA);

            // Step 2: Compute residuals for CI estimation
            List<Double> residuals = new ArrayList<>();
            for (int i = 0; i < historicalCounts.size(); i++) {
                residuals.add(historicalCounts.get(i) - smoothed.get(i));
            }
            double residualStddev = stddev(residuals);

            // Step 3: Trend estimate from last 6 deltas
            double lastSmoothed = smoothed.get(smoothed.size() - 1);
            double trend        = computeTrend(smoothed, 6, lastSmoothed);

            // Step 4: Build hourly forecasts
            List<HourlyForecast> forecasts = new ArrayList<>();
            for (int i = 1; i <= horizon; i++) {
                double predicted  = Math.max(0.0, lastSmoothed * (1.0 + trend * i));
                double halfWidth  = Z_95 * residualStddev;
                double lower      = Math.max(0.0, predicted - halfWidth);
                double upper      = predicted + halfWidth;
                Instant hourSlot  = now.plus(i, ChronoUnit.HOURS);
                forecasts.add(new HourlyForecast(hourSlot,
                        round2(predicted), round2(lower), round2(upper)));
            }

            // Step 5: Confidence — degrades with horizon and residual noise
            double confidence = computeConfidence(historicalCounts.size(), residualStddev, lastSmoothed, horizon);

            log.info("Settlement forecast: horizon={}h historicPoints={} lastSmoothed={} trend={}",
                    horizon, historicalCounts.size(), round2(lastSmoothed), round2(trend));

            return new ForecastResult(
                    forecasts,
                    round2(confidence),
                    "HoltWinters-SimpleES-alpha=" + ALPHA,
                    now
            );

        } catch (Exception e) {
            log.warn("ForecastSettlementService.forecast failed, returning empty forecast: {}", e.getMessage());
            return buildZeroForecast(horizon, now);
        }
    }

    // ── ES query ─────────────────────────────────────────────────────────────

    /**
     * Query clearflow-settlement-* for settlement events in the last {@code lookbackHours}
     * hours, aggregated in 1-hour buckets. Returns counts ordered oldest-first.
     */
    private List<Double> fetchHourlyCounts(int lookbackHours) {
        String query = """
                {
                  "query": {
                    "bool": {
                      "filter": [
                        { "range": { "@timestamp": { "gte": "now-%dh" } } }
                      ]
                    }
                  },
                  "size": 0,
                  "aggs": {
                    "by_hour": {
                      "date_histogram": {
                        "field": "@timestamp",
                        "calendar_interval": "1h",
                        "min_doc_count": 0,
                        "extended_bounds": {
                          "min": "now-%dh",
                          "max": "now"
                        }
                      }
                    }
                  }
                }
                """.formatted(lookbackHours, lookbackHours);

        try {
            // Primary: settlement-specific index
            List<Double> counts = runHistogramQuery(query, "clearflow-settlement-*");
            if (counts.isEmpty()) {
                // Fallback: SETTLEMENT_COMPLETE events from all indices
                counts = runHistogramQuery(buildEventTypeHistogram(lookbackHours), "clearflow-*");
            }
            return counts;
        } catch (Exception e) {
            log.warn("fetchHourlyCounts failed: {}", e.getMessage());
            return Collections.emptyList();
        }
    }

    /** Histogram limited to SETTLEMENT_COMPLETE event type — used as fallback. */
    private String buildEventTypeHistogram(int lookbackHours) {
        return """
                {
                  "query": {
                    "bool": {
                      "filter": [
                        { "term":  { "eventType": "SETTLEMENT_COMPLETE" } },
                        { "range": { "@timestamp": { "gte": "now-%dh" } } }
                      ]
                    }
                  },
                  "size": 0,
                  "aggs": {
                    "by_hour": {
                      "date_histogram": {
                        "field": "@timestamp",
                        "calendar_interval": "1h",
                        "min_doc_count": 0
                      }
                    }
                  }
                }
                """.formatted(lookbackHours);
    }

    private List<Double> runHistogramQuery(String queryBody, String indexPattern) {
        try {
            String url = esUrl + "/" + indexPattern + "/_search";
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .header("Content-Type", "application/json")
                    .timeout(Duration.ofSeconds(10))
                    .POST(HttpRequest.BodyPublishers.ofString(queryBody))
                    .build();

            HttpResponse<String> response = http.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() != 200) {
                log.warn("ES histogram query returned status {} on {}", response.statusCode(), indexPattern);
                return Collections.emptyList();
            }

            JsonNode root    = mapper.readTree(response.body());
            JsonNode buckets = root.path("aggregations").path("by_hour").path("buckets");
            if (!buckets.isArray() || buckets.isEmpty()) {
                return Collections.emptyList();
            }

            List<Double> counts = new ArrayList<>();
            buckets.forEach(b -> counts.add(b.path("doc_count").asDouble(0.0)));
            return counts;

        } catch (Exception e) {
            log.warn("runHistogramQuery failed on {}: {}", indexPattern, e.getMessage());
            return Collections.emptyList();
        }
    }

    // ── Smoothing & statistics ────────────────────────────────────────────────

    private List<Double> exponentialSmooth(List<Double> series, double alpha) {
        List<Double> smoothed = new ArrayList<>(series.size());
        smoothed.add(series.get(0));  // seed with first observed value
        for (int i = 1; i < series.size(); i++) {
            double prev = smoothed.get(i - 1);
            smoothed.add(alpha * series.get(i) + (1.0 - alpha) * prev);
        }
        return smoothed;
    }

    /**
     * Compute normalised trend as the average of the last {@code n} hour-over-hour
     * deltas divided by the last smoothed value. Returns 0 if insufficient data.
     */
    private double computeTrend(List<Double> smoothed, int n, double last) {
        if (last <= 0.0 || smoothed.size() < 2) return 0.0;

        int start = Math.max(1, smoothed.size() - n);
        double sumDeltas = 0.0;
        int count = 0;
        for (int i = start; i < smoothed.size(); i++) {
            sumDeltas += smoothed.get(i) - smoothed.get(i - 1);
            count++;
        }
        if (count == 0) return 0.0;
        return (sumDeltas / count) / last;
    }

    private double stddev(List<Double> values) {
        if (values.size() < 2) return 0.0;
        double mean = values.stream().mapToDouble(Double::doubleValue).average().orElse(0.0);
        double sumSq = values.stream()
                .mapToDouble(v -> (v - mean) * (v - mean))
                .sum();
        return Math.sqrt(sumSq / values.size());
    }

    /**
     * Confidence score (0–1).
     * Penalises low data coverage, high relative noise, and long horizons.
     */
    private double computeConfidence(int dataPoints, double residualStddev,
                                     double lastSmoothed, int horizon) {
        double coverageFactor = Math.min(1.0, dataPoints / 24.0);  // full confidence at 24+ points
        double noiseFactor    = (lastSmoothed > 0.0)
                ? Math.max(0.0, 1.0 - (residualStddev / lastSmoothed))
                : 0.5;
        double horizonFactor  = Math.max(0.1, 1.0 - (horizon / 168.0));
        return round2(coverageFactor * noiseFactor * horizonFactor);
    }

    private ForecastResult buildZeroForecast(int horizon, Instant now) {
        List<HourlyForecast> forecasts = new ArrayList<>();
        for (int i = 1; i <= horizon; i++) {
            forecasts.add(new HourlyForecast(
                    now.plus(i, ChronoUnit.HOURS), 0.0, 0.0, 0.0));
        }
        return new ForecastResult(forecasts, 0.0,
                "HoltWinters-SimpleES-alpha=" + ALPHA + " (no-data)", now);
    }

    private double round2(double v) {
        return Math.round(v * 100.0) / 100.0;
    }
}
