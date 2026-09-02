package com.clearflow.mcp.demo;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Seeds 6 named demo scenarios into Elasticsearch on startup.
 *
 * Why: the MCP /explain endpoint is only impressive if there's real data in ES.
 * Without this, every demo call returns NOT_FOUND. With this seeder, an operator
 * can immediately run `curl .../explain/PAY-DEMO-AML-001` and see full root cause.
 *
 * Idempotent: checks if the sentinel doc PAY-DEMO-SENTINEL already exists;
 * skips seeding if found. Safe to restart without duplicating data.
 *
 * Scenarios seeded:
 *   PAY-DEMO-AML-001       — AML sanctions hit (GAZPROMBANK, matchScore=0.94)
 *   PAY-DEMO-FRAUD-001     — Fraud score CRITICAL (score=0.97)
 *   PAY-DEMO-SETTLED-001   — Full clean settlement (happy path)
 *   PAY-DEMO-EMBARGO-001   — Embargo hit at validation stage
 *   PAY-DEMO-ROUTING-001   — Rail routing failure (no viable rail)
 *   PAY-DEMO-STORM-*       — 10 payments each with HIGH alerts (systemic detection demo)
 */
@Component
public class DemoScenarioSeeder implements ApplicationRunner {

    private static final Logger log = LoggerFactory.getLogger(DemoScenarioSeeder.class);
    private static final String DEMO_INDEX = "clearflow-demo";
    private static final String SENTINEL_ID = "PAY-DEMO-SENTINEL";

    private final String esUrl;
    private final ObjectMapper mapper;
    private final HttpClient http;

    public DemoScenarioSeeder(
            @Value("${clearflow.elasticsearch.url:http://localhost:9200}") String esUrl,
            ObjectMapper mapper) {
        this.esUrl = esUrl;
        this.mapper = mapper;
        this.http = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build();
    }

    @Override
    public void run(ApplicationArguments args) {
        if (!isEsAvailable()) {
            log.info("Elasticsearch not available — skipping demo scenario seeding");
            return;
        }
        if (isAlreadySeeded()) {
            log.info("Demo scenarios already seeded — skipping");
            return;
        }

        log.info("Seeding ClearFlow demo scenarios into Elasticsearch index '{}'", DEMO_INDEX);
        List<Map<String, Object>> docs = buildAllScenarios();
        int seeded = bulkIndex(docs);
        indexSentinel();
        log.info("Demo seeding complete — {} log documents written to {}", seeded, DEMO_INDEX);
    }

    // ── Scenario builders ─────────────────────────────────────────────────────

    private List<Map<String, Object>> buildAllScenarios() {
        Instant base = Instant.now().truncatedTo(ChronoUnit.SECONDS);
        List<Map<String, Object>> docs = new ArrayList<>();

        docs.addAll(scenarioAmlHit(base));
        docs.addAll(scenarioFraudCritical(base.plusSeconds(60)));
        docs.addAll(scenarioSettled(base.plusSeconds(120)));
        docs.addAll(scenarioEmbargo(base.plusSeconds(180)));
        docs.addAll(scenarioRoutingFailure(base.plusSeconds(240)));
        docs.addAll(scenarioAlertStorm(base.plusSeconds(300)));

        return docs;
    }

    /** Scenario 1: AML sanctions hit — GAZPROMBANK, matchScore=0.94 */
    private List<Map<String, Object>> scenarioAmlHit(Instant t) {
        String id = "PAY-DEMO-AML-001";
        return List.of(
                doc(id, "gateway",               t,      "INFO",  "PAYMENT_SUBMITTED",    "Payment submitted", null, null, null, null, null, null, "DE", "RU", "EUR", 750000.0),
                doc(id, "validation-enrichment", t.plusSeconds(1), "INFO", "IBAN_VALIDATED", "IBAN validated OK", null, null, null, null, null, null, "DE", "RU", "EUR", null),
                doc(id, "validation-enrichment", t.plusSeconds(1), "INFO", "EMBARGO_CHECK",  "Embargo check: no hit", null, null, null, null, null, null, "DE", "RU", "EUR", null),
                doc(id, "fraud-scoring",          t.plusSeconds(2), "INFO", "FRAUD_SCORE_COMPUTED", "Fraud score computed", 0.31, "MEDIUM", null, null, null, null, null, null, "EUR", null),
                doc(id, "aml-compliance",         t.plusSeconds(3), "WARN", "AML_SANCTIONS_HIT", "AML sanctions match: GAZPROMBANK", null, null, "HIT", 0.94, "GAZPROMBANK", null, null, null, "EUR", null),
                doc(id, "audit",                  t.plusSeconds(4), "INFO", "AUDIT_CHAIN_APPENDED", "Audit record created", null, null, null, null, null, null, null, null, "EUR", null)
        );
    }

    /** Scenario 2: Fraud score CRITICAL — velocity + high score */
    private List<Map<String, Object>> scenarioFraudCritical(Instant t) {
        String id = "PAY-DEMO-FRAUD-001";
        return List.of(
                doc(id, "gateway",       t,               "INFO", "PAYMENT_SUBMITTED",    "Payment submitted", null, null, null, null, null, null, "GB", "NG", "GBP", 95000.0),
                doc(id, "validation-enrichment", t.plusSeconds(1), "INFO", "PAYMENT_VALIDATED", "Validation passed", null, null, null, null, null, null, "GB", "NG", "GBP", null),
                doc(id, "fraud-scoring", t.plusSeconds(2), "WARN", "FRAUD_SCORE_COMPUTED", "CRITICAL fraud score: velocity + off-hours", 0.97, "CRITICAL", null, null, null, null, "GB", "NG", "GBP", null),
                doc(id, "fraud-scoring", t.plusSeconds(2), "WARN", "PAYMENT_BLOCKED", "Payment blocked: CRITICAL fraud score", null, null, null, null, null, null, "GB", "NG", "GBP", null),
                doc(id, "audit",         t.plusSeconds(3), "INFO", "AUDIT_CHAIN_APPENDED", "Audit record created", null, null, null, null, null, null, null, null, "GBP", null)
        );
    }

    /** Scenario 3: Happy path — full settlement */
    private List<Map<String, Object>> scenarioSettled(Instant t) {
        String id = "PAY-DEMO-SETTLED-001";
        return List.of(
                doc(id, "gateway",               t,               "INFO", "PAYMENT_SUBMITTED",    "Payment submitted", null, null, null, null, null, null, "NL", "DE", "EUR", 22000.0),
                doc(id, "validation-enrichment", t.plusSeconds(1), "INFO", "IBAN_VALIDATED",       "IBAN validated", null, null, null, null, null, null, "NL", "DE", "EUR", null),
                doc(id, "validation-enrichment", t.plusSeconds(1), "INFO", "PAYMENT_VALIDATED",    "Validation passed", null, null, null, null, null, null, "NL", "DE", "EUR", null),
                doc(id, "fraud-scoring",          t.plusSeconds(2), "INFO", "FRAUD_SCORE_COMPUTED", "Low risk", 0.08, "LOW", null, null, null, null, "NL", "DE", "EUR", null),
                doc(id, "aml-compliance",         t.plusSeconds(3), "INFO", "AML_SCREENING_COMPLETE", "AML clear", null, null, "CLEAR", null, null, null, "NL", "DE", "EUR", null),
                doc(id, "routing-execution",      t.plusSeconds(4), "INFO", "RAIL_SELECTED",        "Rail selected: SEPA_INSTANT", null, null, null, null, null, "SEPA_INSTANT", "NL", "DE", "EUR", null),
                doc(id, "routing-execution",      t.plusSeconds(4), "INFO", "PAYMENT_ROUTED",       "Payment routed via SEPA_INSTANT", null, null, null, null, null, "SEPA_INSTANT", "NL", "DE", "EUR", null),
                doc(id, "settlement",             t.plusSeconds(5), "INFO", "SETTLEMENT_COMPLETE",  "Settlement complete", null, null, null, null, null, "SEPA_INSTANT", "NL", "DE", "EUR", null),
                doc(id, "audit",                  t.plusSeconds(6), "INFO", "AUDIT_CHAIN_APPENDED", "Audit record created", null, null, null, null, null, null, null, null, "EUR", null)
        );
    }

    /** Scenario 4: Embargo hit at validation */
    private List<Map<String, Object>> scenarioEmbargo(Instant t) {
        String id = "PAY-DEMO-EMBARGO-001";
        return List.of(
                doc(id, "gateway",               t,               "INFO", "PAYMENT_SUBMITTED", "Payment submitted", null, null, null, null, null, null, "US", "IR", "USD", 2000000.0),
                doc(id, "validation-enrichment", t.plusSeconds(1), "WARN", "EMBARGO_HIT",       "Embargo hit: destination country IR under OFAC sanctions", null, null, null, null, null, null, "US", "IR", "USD", null),
                doc(id, "validation-enrichment", t.plusSeconds(1), "WARN", "PAYMENT_REJECTED",  "Payment rejected: embargo", null, null, null, null, null, null, "US", "IR", "USD", null),
                doc(id, "audit",                 t.plusSeconds(2), "INFO", "AUDIT_CHAIN_APPENDED", "Audit record created", null, null, null, null, null, null, null, null, "USD", null)
        );
    }

    /** Scenario 5: Routing failure — no viable rail */
    private List<Map<String, Object>> scenarioRoutingFailure(Instant t) {
        String id = "PAY-DEMO-ROUTING-001";
        return List.of(
                doc(id, "gateway",               t,               "INFO", "PAYMENT_SUBMITTED",    "Payment submitted", null, null, null, null, null, null, "JP", "BR", "JPY", 18000000.0),
                doc(id, "validation-enrichment", t.plusSeconds(1), "INFO", "PAYMENT_VALIDATED",    "Validation passed", null, null, null, null, null, null, "JP", "BR", "JPY", null),
                doc(id, "fraud-scoring",          t.plusSeconds(2), "INFO", "FRAUD_SCORE_COMPUTED", "Low risk", 0.12, "LOW", null, null, null, null, "JP", "BR", "JPY", null),
                doc(id, "aml-compliance",         t.plusSeconds(3), "INFO", "AML_SCREENING_COMPLETE", "AML clear", null, null, "CLEAR", null, null, null, "JP", "BR", "JPY", null),
                doc(id, "routing-execution",      t.plusSeconds(4), "ERROR", "ROUTING_FAILED",     "No viable rail: JPY→BRL conversion unavailable, SWIFT_GPI timeout", null, null, null, null, null, null, "JP", "BR", "JPY", null),
                doc(id, "routing-execution",      t.plusSeconds(4), "ERROR", "PAYMENT_FAILED",     "Payment failed: routing exhausted all rail options", null, null, null, null, null, null, "JP", "BR", "JPY", null),
                doc(id, "audit",                  t.plusSeconds(5), "INFO", "AUDIT_CHAIN_APPENDED", "Audit record created", null, null, null, null, null, null, null, null, "JPY", null)
        );
    }

    /** Scenario 6: Alert storm — 10 payments with HIGH alertLevel (systemic detection demo) */
    private List<Map<String, Object>> scenarioAlertStorm(Instant t) {
        List<Map<String, Object>> docs = new ArrayList<>();
        String[] services = {"fraud-scoring", "aml-compliance", "settlement", "routing-execution"};
        for (int i = 1; i <= 10; i++) {
            String id = String.format("PAY-DEMO-STORM-%03d", i);
            String service = services[i % services.length];
            Map<String, Object> d = new LinkedHashMap<>();
            d.put("@timestamp", t.plusSeconds(i * 5).toString());
            d.put("paymentId", id);
            d.put("service", service);
            d.put("level", "WARN");
            d.put("alertLevel", "HIGH");
            d.put("eventType", "PAYMENT_BLOCKED");
            d.put("message", "Storm payment " + i + " blocked by " + service);
            d.put("debtorCountry", "US");
            d.put("creditorCountry", "RU");
            d.put("currency", "USD");
            docs.add(d);
        }
        return docs;
    }

    // ── Document builder ──────────────────────────────────────────────────────

    private Map<String, Object> doc(String paymentId, String service, Instant ts,
                                     String level, String eventType, String message,
                                     Double fraudScore, String riskBand,
                                     String screeningResult, Double matchScore, String listHit,
                                     String rail,
                                     String debtorCountry, String creditorCountry,
                                     String currency, Double amount) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("@timestamp", ts.toString());
        m.put("paymentId", paymentId);
        m.put("service", service);
        m.put("level", level);
        m.put("eventType", eventType);
        m.put("message", message);
        if (fraudScore != null)      m.put("fraudScore", fraudScore);
        if (riskBand != null)        m.put("riskBand", riskBand);
        if (screeningResult != null) m.put("screeningResult", screeningResult);
        if (matchScore != null)      m.put("matchScore", matchScore);
        if (listHit != null)         m.put("listHit", listHit);
        if (rail != null)            m.put("rail", rail);
        if (debtorCountry != null)   m.put("debtorCountry", debtorCountry);
        if (creditorCountry != null) m.put("creditorCountry", creditorCountry);
        if (currency != null)        m.put("currency", currency);
        if (amount != null)          m.put("amount", amount);
        return m;
    }

    // ── Elasticsearch operations ──────────────────────────────────────────────

    private boolean isEsAvailable() {
        try {
            HttpRequest req = HttpRequest.newBuilder()
                    .uri(URI.create(esUrl + "/_cluster/health"))
                    .timeout(Duration.ofSeconds(3))
                    .GET().build();
            HttpResponse<String> resp = http.send(req, HttpResponse.BodyHandlers.ofString());
            return resp.statusCode() == 200;
        } catch (Exception e) {
            return false;
        }
    }

    private boolean isAlreadySeeded() {
        try {
            HttpRequest req = HttpRequest.newBuilder()
                    .uri(URI.create(esUrl + "/" + DEMO_INDEX + "/_doc/" + SENTINEL_ID))
                    .timeout(Duration.ofSeconds(3))
                    .GET().build();
            HttpResponse<String> resp = http.send(req, HttpResponse.BodyHandlers.ofString());
            return resp.statusCode() == 200;
        } catch (Exception e) {
            return false;
        }
    }

    private void indexSentinel() {
        try {
            String body = mapper.writeValueAsString(Map.of(
                    "@timestamp", Instant.now().toString(),
                    "paymentId", SENTINEL_ID,
                    "service", "demo-seeder",
                    "level", "INFO",
                    "message", "Demo scenarios seeded"
            ));
            post(esUrl + "/" + DEMO_INDEX + "/_doc/" + SENTINEL_ID, body);
        } catch (Exception e) {
            log.warn("Failed to write sentinel doc: {}", e.getMessage());
        }
    }

    private int bulkIndex(List<Map<String, Object>> docs) {
        try {
            StringBuilder bulk = new StringBuilder();
            for (Map<String, Object> doc : docs) {
                bulk.append("{\"index\":{\"_index\":\"").append(DEMO_INDEX).append("\"}}\n");
                bulk.append(mapper.writeValueAsString(doc)).append("\n");
            }
            int status = post(esUrl + "/_bulk", bulk.toString());
            if (status >= 200 && status < 300) {
                return docs.size();
            }
            log.warn("Bulk index returned status {}", status);
            return 0;
        } catch (Exception e) {
            log.warn("Bulk index failed: {}", e.getMessage());
            return 0;
        }
    }

    private int post(String url, String body) throws Exception {
        HttpRequest req = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .header("Content-Type", "application/json")
                .timeout(Duration.ofSeconds(10))
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();
        return http.send(req, HttpResponse.BodyHandlers.ofString()).statusCode();
    }
}
