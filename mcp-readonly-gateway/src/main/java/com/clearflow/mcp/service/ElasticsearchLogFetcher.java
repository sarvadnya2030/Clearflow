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
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;

/**
 * Queries Elasticsearch for payment log events across all clearflow-* indices.
 *
 * At a bank, a single payment generates 40–80 log entries across 7 services.
 * This fetcher retrieves all of them in one multi-index query, sorted by
 * timestamp, giving downstream components the raw material for timeline
 * reconstruction and root cause analysis.
 *
 * Graceful degradation: if ES is unavailable, returns an empty list rather
 * than throwing — the caller decides how to handle missing data.
 */
@Service
public class ElasticsearchLogFetcher {

    private static final Logger log = LoggerFactory.getLogger(ElasticsearchLogFetcher.class);

    /**
     * A single log entry retrieved from Elasticsearch.
     * All fields are nullable — not every service emits every field.
     */
    public record LogEntry(
            String timestamp,       // @timestamp ISO8601
            String service,         // gateway | fraud-scoring | aml-compliance | ...
            String level,           // INFO | WARN | ERROR
            String message,         // raw log message
            String paymentId,
            String correlationId,
            String traceId,
            String eventType,       // PAYMENT_SUBMITTED | FRAUD_SCORE_COMPUTED | ...
            String alertLevel,      // HIGH | MEDIUM | LOW
            // fraud-scoring fields
            Double fraudScore,
            String riskBand,
            // aml-compliance fields
            String screeningResult, // HIT | CLEAR
            Double matchScore,
            String listHit,         // matched SDN/PEP entry name
            // routing/settlement fields
            String rail,
            // timing
            Long durationMs,
            // payment context (from gateway)
            String debtorCountry,
            String creditorCountry,
            String currency,
            Double amount
    ) {}

    private final String esUrl;
    private final String indexPattern;
    private final int maxEntries;
    private final ObjectMapper mapper;
    private final HttpClient http;

    public ElasticsearchLogFetcher(
            @Value("${clearflow.elasticsearch.url:http://localhost:9200}") String esUrl,
            @Value("${clearflow.elasticsearch.index-pattern:clearflow-*}") String indexPattern,
            @Value("${clearflow.elasticsearch.max-log-entries:200}") int maxEntries,
            ObjectMapper mapper) {
        this.esUrl = esUrl;
        this.indexPattern = indexPattern;
        this.maxEntries = maxEntries;
        this.mapper = mapper;
        this.http = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .build();
    }

    /**
     * Fetch all log entries for a specific paymentId across all service indices.
     * Returns entries sorted by @timestamp ascending (oldest first).
     */
    public List<LogEntry> fetchLogsForPayment(String paymentId) {
        String query = buildPaymentQuery(paymentId, maxEntries);
        return executeQuery(query, "paymentId=" + paymentId);
    }

    /**
     * Fetch recent logs for a specific service (for health / systemic checks).
     */
    public List<LogEntry> fetchServiceLogs(String service, int minutes) {
        String query = buildServiceQuery(service, minutes, 100);
        return executeQuery(query, "service=" + service + " last=" + minutes + "m");
    }

    /**
     * Count log entries grouped by a field value — used for systemic detection.
     * Returns a map of fieldValue → count, sorted by count descending.
     */
    public Map<String, Long> countByEventType(String service, int minutes) {
        String query = buildAggregationQuery(service, "eventType", minutes);
        return executeAggregation(query, "eventType");
    }

    /**
     * Count HIGH alertLevel events per service in the last N minutes.
     */
    public Map<String, Long> countAlertsByService(int minutes) {
        String query = buildAlertAggregationQuery(minutes);
        return executeAggregation(query, "service");
    }

    /**
     * Count values of an arbitrary keyword field in the last N minutes.
     */
    public Map<String, Long> countByField(String fieldKeyword, int minutes) {
        return executeAggregation(buildAggregationQuery(null, fieldKeyword, minutes), fieldKeyword);
    }

    /**
     * Compute average durationMs for events in the last N minutes.
     * Returns 0.0 if field is missing or no data.
     */
    public double averageDuration(int minutes) {
        String query = """
                {
                  "query": {
                    "bool": {
                      "filter": [
                        { "range": { "@timestamp": { "gte": "now-%dm" } } },
                        { "exists": { "field": "durationMs" } }
                      ]
                    }
                  },
                  "size": 0,
                  "aggs": {
                    "avg_duration": { "avg": { "field": "durationMs" } }
                  }
                }
                """.formatted(minutes);

        try {
            String url = esUrl + "/" + indexPattern + "/_search";
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .header("Content-Type", "application/json")
                    .timeout(Duration.ofSeconds(10))
                    .POST(HttpRequest.BodyPublishers.ofString(query))
                    .build();

            HttpResponse<String> response = http.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() != 200) return 0.0;
            JsonNode root = mapper.readTree(response.body());
            JsonNode avg = root.path("aggregations").path("avg_duration").path("value");
            return avg.isNumber() ? avg.doubleValue() : 0.0;
        } catch (Exception e) {
            log.warn("ES averageDuration failed: {}", e.getMessage());
            return 0.0;
        }
    }

    // ── Fleet-level / ops queries ─────────────────────────────────────────────

    /**
     * Search payments by criteria — riskBand, fraudPattern, finalStatus, creditorCountry.
     * All filters are optional (pass null to skip). Returns up to {@code limit} gateway events.
     */
    public List<LogEntry> searchPayments(String riskBand, String fraudPattern,
                                         String finalStatus, String creditorCountry,
                                         int minutes, int limit) {
        StringBuilder filters = new StringBuilder();
        filters.append("""
                { "range": { "@timestamp": { "gte": "now-%dm" } } }
                """.formatted(minutes));
        if (riskBand != null && !riskBand.isBlank())
            filters.append(", { \"term\": { \"riskBand\": \"" + riskBand + "\" } }");
        if (fraudPattern != null && !fraudPattern.isBlank())
            filters.append(", { \"term\": { \"fraudPattern\": \"" + fraudPattern + "\" } }");
        if (finalStatus != null && !finalStatus.isBlank())
            filters.append(", { \"term\": { \"finalStatus\": \"" + finalStatus + "\" } }");
        if (creditorCountry != null && !creditorCountry.isBlank())
            filters.append(", { \"term\": { \"creditorCountry\": \"" + creditorCountry + "\" } }");

        String query = """
                {
                  "query": { "bool": { "filter": [ %s ] } },
                  "sort": [ { "@timestamp": "desc" } ],
                  "size": %d
                }
                """.formatted(filters, limit);
        return executeQuery(query, "searchPayments");
    }

    /**
     * Per-service health: event counts, error counts, and alert counts in last N minutes.
     * Returns a map of service → sub-metrics.
     */
    public Map<String, Map<String, Long>> serviceHealthSnapshot(int minutes) {
        String[] services = {"gateway","validation-enrichment","fraud-scoring",
                             "aml-compliance","routing-execution","settlement","audit"};
        Map<String, Map<String, Long>> result = new java.util.LinkedHashMap<>();
        for (String svc : services) {
            Map<String, Long> events  = countByEventType(svc, minutes);
            Map<String, Long> alerts  = countAlertsByService(minutes);
            long errorCount = events.entrySet().stream()
                    .filter(e -> e.getKey().contains("ERROR") || e.getKey().contains("BLOCKED")
                            || e.getKey().contains("SANCTIONS_HIT"))
                    .mapToLong(Map.Entry::getValue).sum();
            long total = events.values().stream().mapToLong(Long::longValue).sum();
            Map<String, Long> health = new java.util.LinkedHashMap<>();
            health.put("totalEvents",  total);
            health.put("errorEvents",  errorCount);
            health.put("highAlerts",   alerts.getOrDefault(svc, 0L));
            result.put(svc, health);
        }
        return result;
    }

    /**
     * Fetch HIGH-alertLevel events from clearflow-alerts-* index, newest first.
     */
    public List<LogEntry> fetchAlertQueue(int limit) {
        String query = """
                {
                  "query": {
                    "bool": {
                      "filter": [
                        { "term": { "alertLevel": "HIGH" } }
                      ]
                    }
                  },
                  "sort": [ { "@timestamp": "desc" } ],
                  "size": %d
                }
                """.formatted(limit);
        // Query alerts index specifically
        try {
            String url = esUrl + "/clearflow-alerts-*/_search";
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .header("Content-Type", "application/json")
                    .timeout(Duration.ofSeconds(10))
                    .POST(HttpRequest.BodyPublishers.ofString(query))
                    .build();
            HttpResponse<String> resp = http.send(request, HttpResponse.BodyHandlers.ofString());
            if (resp.statusCode() != 200) return Collections.emptyList();
            return parseHits(mapper.readTree(resp.body()));
        } catch (Exception e) {
            log.warn("fetchAlertQueue failed: {}", e.getMessage());
            return Collections.emptyList();
        }
    }

    /**
     * Aggregate payment outcome metrics: total events, settled, blocked, fraud rate,
     * AML hit rate, embargo rate in the last N minutes across all service indices.
     */
    public Map<String, Object> paymentMetrics(int minutes) {
        Map<String, Object> metrics = new java.util.LinkedHashMap<>();
        Map<String, Long> byEvent   = countByEventType(null, minutes);
        Map<String, Long> byRisk    = countByField("riskBand", minutes);
        Map<String, Long> byPattern = countByField("fraudPattern", minutes);
        Map<String, Long> alerts    = countAlertsByService(minutes);

        long submitted  = byEvent.getOrDefault("PAYMENT_SUBMITTED",  0L);
        long settled    = byEvent.getOrDefault("SETTLEMENT_COMPLETE", 0L);
        long amlHit     = byEvent.getOrDefault("AML_SANCTIONS_HIT",  0L);
        long blocked    = byEvent.getOrDefault("PAYMENT_STATUS_UPDATE", 0L);
        long critical   = byRisk.getOrDefault("CRITICAL", 0L);
        long highAlerts = alerts.values().stream().mapToLong(Long::longValue).sum();

        metrics.put("windowMinutes",   minutes);
        metrics.put("paymentsSubmitted", submitted);
        metrics.put("settled",           settled);
        metrics.put("settlementRate",    submitted > 0 ? String.format("%.1f%%", settled * 100.0 / submitted) : "n/a");
        metrics.put("amlHits",           amlHit);
        metrics.put("amlHitRate",        submitted > 0 ? String.format("%.2f%%", amlHit * 100.0 / submitted) : "n/a");
        metrics.put("fraudCritical",     critical);
        metrics.put("fraudRate",         submitted > 0 ? String.format("%.2f%%", critical * 100.0 / submitted) : "n/a");
        metrics.put("blocked",           blocked);
        metrics.put("highAlerts",        highAlerts);
        metrics.put("eventsByType",      byEvent);
        metrics.put("fraudPatterns",     byPattern);
        metrics.put("riskBands",         byRisk);
        return metrics;
    }

    /**
     * Find all distinct paymentIds that share a given eventType (e.g. AML_SANCTIONS_HIT)
     * in the last N minutes. Used for triage — "how many payments hit the same failure?"
     */
    public Map<String, Object> triageByEventType(String eventType, int minutes) {
        String query = """
                {
                  "query": {
                    "bool": {
                      "filter": [
                        { "term":  { "eventType": "%s" } },
                        { "range": { "@timestamp": { "gte": "now-%dm" } } }
                      ]
                    }
                  },
                  "size": 0,
                  "aggs": {
                    "by_service": { "terms": { "field": "service", "size": 10 } },
                    "by_country": { "terms": { "field": "creditorCountry", "size": 10 } },
                    "by_pattern": { "terms": { "field": "fraudPattern", "size": 10 } },
                    "total_amount": { "sum": { "field": "amount" } }
                  }
                }
                """.formatted(eventType, minutes);
        try {
            String url = esUrl + "/" + indexPattern + "/_search";
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .header("Content-Type", "application/json")
                    .timeout(Duration.ofSeconds(15))
                    .POST(HttpRequest.BodyPublishers.ofString(query))
                    .build();
            HttpResponse<String> resp = http.send(request, HttpResponse.BodyHandlers.ofString());
            if (resp.statusCode() != 200) return Map.of("error", "ES returned " + resp.statusCode());
            JsonNode root = mapper.readTree(resp.body());
            long total = root.path("hits").path("total").path("value").asLong();
            JsonNode aggs = root.path("aggregations");
            Map<String, Object> result = new java.util.LinkedHashMap<>();
            result.put("eventType",   eventType);
            result.put("windowMinutes", minutes);
            result.put("totalHits",   total);
            result.put("totalAmount", aggs.path("total_amount").path("value").asDouble());
            result.put("byService",   buckets(aggs.path("by_service")));
            result.put("byCountry",   buckets(aggs.path("by_country")));
            result.put("byPattern",   buckets(aggs.path("by_pattern")));
            return result;
        } catch (Exception e) {
            log.warn("triageByEventType failed: {}", e.getMessage());
            return Map.of("error", e.getMessage());
        }
    }

    private Map<String, Long> buckets(JsonNode agg) {
        Map<String, Long> m = new java.util.LinkedHashMap<>();
        agg.path("buckets").forEach(b -> m.put(b.path("key").asText(), b.path("doc_count").asLong()));
        return m;
    }

    // ── Query builders ────────────────────────────────────────────────────────

    private String buildPaymentQuery(String paymentId, int size) {
        // Multi-index term query on paymentId, sorted by timestamp
        return """
                {
                  "query": {
                    "bool": {
                      "filter": [
                        { "term": { "paymentId": "%s" } }
                      ]
                    }
                  },
                  "sort": [ { "@timestamp": "asc" } ],
                  "size": %d
                }
                """.formatted(paymentId.replace("\"", ""), size);
    }

    private String buildServiceQuery(String service, int minutes, int size) {
        return """
                {
                  "query": {
                    "bool": {
                      "filter": [
                        { "term":  { "service": "%s" } },
                        { "range": { "@timestamp": { "gte": "now-%dm" } } }
                      ]
                    }
                  },
                  "sort": [ { "@timestamp": "desc" } ],
                  "size": %d
                }
                """.formatted(service, minutes, size);
    }

    private String buildAggregationQuery(String service, String aggField, int minutes) {
        String serviceFilter = service != null
                ? """
                  { "term": { "service": "%s" } },
                  """.formatted(service)
                : "";
        return """
                {
                  "query": {
                    "bool": {
                      "filter": [
                        %s
                        { "range": { "@timestamp": { "gte": "now-%dm" } } }
                      ]
                    }
                  },
                  "size": 0,
                  "aggs": {
                    "by_field": {
                      "terms": { "field": "%s", "size": 50 }
                    }
                  }
                }
                """.formatted(serviceFilter, minutes, aggField);
    }

    private String buildAlertAggregationQuery(int minutes) {
        return """
                {
                  "query": {
                    "bool": {
                      "filter": [
                        { "term":  { "alertLevel": "HIGH" } },
                        { "range": { "@timestamp": { "gte": "now-%dm" } } }
                      ]
                    }
                  },
                  "size": 0,
                  "aggs": {
                    "by_field": {
                      "terms": { "field": "service", "size": 20 }
                    }
                  }
                }
                """.formatted(minutes);
    }

    // ── HTTP execution ────────────────────────────────────────────────────────

    private List<LogEntry> executeQuery(String queryBody, String context) {
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
                log.warn("ES query returned status {} for {}", response.statusCode(), context);
                return Collections.emptyList();
            }

            return parseHits(mapper.readTree(response.body()));

        } catch (Exception e) {
            log.warn("ES unavailable for {} — returning empty log list: {}", context, e.getMessage());
            return Collections.emptyList();
        }
    }

    private Map<String, Long> executeAggregation(String queryBody, String aggFieldName) {
        try {
            String url = esUrl + "/" + indexPattern + "/_search";
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .header("Content-Type", "application/json")
                    .timeout(Duration.ofSeconds(10))
                    .POST(HttpRequest.BodyPublishers.ofString(queryBody))
                    .build();

            HttpResponse<String> response = http.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() != 200) return Collections.emptyMap();

            JsonNode root = mapper.readTree(response.body());
            JsonNode buckets = root.path("aggregations").path("by_field").path("buckets");
            if (!buckets.isArray()) return Collections.emptyMap();

            java.util.LinkedHashMap<String, Long> result = new java.util.LinkedHashMap<>();
            buckets.forEach(b -> result.put(
                    b.path("key").asText(),
                    b.path("doc_count").asLong()));
            return result;

        } catch (Exception e) {
            log.warn("ES aggregation failed: {}", e.getMessage());
            return Collections.emptyMap();
        }
    }

    // ── Response parsing ──────────────────────────────────────────────────────

    private List<LogEntry> parseHits(JsonNode root) {
        JsonNode hits = root.path("hits").path("hits");
        if (!hits.isArray()) return Collections.emptyList();

        List<LogEntry> entries = new ArrayList<>();
        hits.forEach(hit -> {
            JsonNode src = hit.path("_source");
            entries.add(new LogEntry(
                    text(src, "@timestamp"),
                    text(src, "service"),
                    text(src, "level"),
                    text(src, "message"),
                    text(src, "paymentId"),
                    text(src, "correlationId"),
                    text(src, "traceId"),
                    text(src, "eventType"),
                    text(src, "alertLevel"),
                    dbl(src, "fraudScore"),
                    text(src, "riskBand"),
                    text(src, "screeningResult"),
                    dbl(src, "matchScore"),
                    text(src, "listHit"),
                    text(src, "rail"),
                    lng(src, "durationMs"),
                    text(src, "debtorCountry"),
                    text(src, "creditorCountry"),
                    text(src, "currency"),
                    dbl(src, "amount")
            ));
        });
        return entries;
    }

    // ── Field extractors (null-safe) ──────────────────────────────────────────

    private String text(JsonNode node, String field) {
        JsonNode v = node.path(field);
        return v.isMissingNode() || v.isNull() ? null : v.asText();
    }

    private Double dbl(JsonNode node, String field) {
        JsonNode v = node.path(field);
        return v.isMissingNode() || v.isNull() ? null : v.asDouble();
    }

    private Long lng(JsonNode node, String field) {
        JsonNode v = node.path(field);
        return v.isMissingNode() || v.isNull() ? null : v.asLong();
    }
}
