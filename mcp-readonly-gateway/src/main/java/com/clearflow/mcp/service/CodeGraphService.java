package com.clearflow.mcp.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.File;
import java.util.*;
import java.util.stream.Collectors;

// java.util.* covers ArrayList, Arrays, Collections, LinkedHashMap, HashMap, List, Map

/**
 * Loads the Graphify code knowledge graph (graphify-out/graph.json) AND the
 * broker topology (graphify-out/queue_topology.json) at startup.
 *
 * Exposes two layers of context for the MCP incident tools:
 *   1. Code graph — which Java classes/methods own each service
 *   2. Broker topology — which Kafka topics / ActiveMQ queues each service
 *      produces to and consumes from, circuit breaker config, saga flow
 *
 * Together these let the LLM trace a cascading failure across service
 * boundaries: "Circuit breaker KAFKA opened in KafkaEventPublisher.java →
 * fallback to ActiveMQPublisher → CLEARFLOW.PAYMENT.INITIATED backed up →
 * ValidationEnrichmentCamelRoute starved → DLQ overflow after 3 retries"
 */
@Service
public class CodeGraphService {

    private static final Logger log = LoggerFactory.getLogger(CodeGraphService.class);

    // Service name → list of class-level graph nodes
    private final Map<String, List<CodeNode>> serviceIndex = new LinkedHashMap<>();

    // Failure keyword → list of relevant class nodes (cross-service)
    private final Map<String, List<CodeNode>> failureIndex = new LinkedHashMap<>();

    // All class-level nodes by label (lower-cased) for quick lookup
    private final Map<String, CodeNode> classByLabel = new LinkedHashMap<>();

    // Broker topology: topic/queue name → QueueNode
    private final Map<String, QueueNode> queueIndex = new LinkedHashMap<>();

    // Service → queues it produces to or consumes from
    private final Map<String, List<QueueNode>> serviceQueueMap = new LinkedHashMap<>();

    // Raw pipeline flow steps from topology JSON
    private final List<String> pipelineFlow = new ArrayList<>();

    // Saga flow description
    private String sagaFlowSummary = "";

    // DLQ config summary
    private String dlqConfigSummary = "";

    // Circuit breaker descriptions (name → description)
    private final Map<String, String> circuitBreakerDesc = new LinkedHashMap<>();

    private boolean loaded = false;
    private boolean topologyLoaded = false;

    @Value("${clearflow.code-graph.path:../graphify-out/graph.json}")
    private String graphPath;

    private final ObjectMapper mapper;

    public CodeGraphService(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    /**
     * A single class-level node from the code graph.
     */
    public record CodeNode(
            String id,
            String label,       // class or file name
            String sourceFile,  // relative path from repo root
            String module,      // derived microservice name
            List<String> methods // method names declared in this class
    ) {}

    /**
     * A message queue/topic node from the broker topology.
     */
    public record QueueNode(
            String name,
            String broker,          // KAFKA | ACTIVEMQ | SOLACE
            String purpose,
            boolean isDLQ,
            boolean isSagaTrigger,
            List<String> producerServices,
            List<String> producerClasses,
            List<String> producerFiles,
            List<String> consumerServices,
            List<String> consumerClasses,
            List<String> consumerFiles
    ) {}

    @PostConstruct
    public void load() {
        loadCodeGraph();
        loadBrokerTopology();
    }

    // service -> service -> aggregated weighted coupling strength, built once
    // from graph.json's real edges (calls/imports/references/shares_data_with),
    // not the flat per-service class lists above. Powers computeBlastRadius /
    // rankRootCausesByBlastRadius -- real multi-hop graph traversal, not a
    // lookup or a vector-similarity nearest-neighbor.
    private final Map<String, Map<String, Double>> moduleGraph = new LinkedHashMap<>();

    // List, not Set -- order matters for tie-breaking below, kept in sync
    // with CascadeFailureDetector's own PIPELINE_ORDER/TOPOLOGY_TIE_MARGIN
    // deliberately (same convention, not a coincidence).
    private static final List<String> DIAGNOSABLE = List.of(
            "gateway", "validation-enrichment", "aml-compliance", "routing-execution", "settlement");

    // Relative importance of each real edge relation for structural coupling.
    // "contains"/"method" are containment, not coupling (a class containing a
    // method tells you nothing about which OTHER service is affected) --
    // excluded entirely rather than down-weighted to zero noise. Doc-level
    // inferred relations (conceptually_related_to, semantically_similar_to,
    // rationale_for, cites) get a low but nonzero weight since they still
    // reflect real graphify-extracted relationships, just weaker evidence
    // than an actual method call.
    private static final Map<String, Double> RELATION_WEIGHT = Map.ofEntries(
            Map.entry("calls", 1.0),
            Map.entry("shares_data_with", 0.9),
            Map.entry("implements", 0.7),
            Map.entry("inherits", 0.7),
            Map.entry("imports", 0.6),
            Map.entry("imports_from", 0.6),
            Map.entry("references", 0.5),
            Map.entry("conceptually_related_to", 0.15),
            Map.entry("semantically_similar_to", 0.15),
            Map.entry("rationale_for", 0.1),
            Map.entry("cites", 0.1)
    );

    private void loadCodeGraph() {
        File f = new File(graphPath);
        if (!f.exists()) {
            f = new File("/home/admin-/Desktop/EDI6/clearflow/graphify-out/graph.json");
        }
        if (!f.exists()) {
            log.warn("CodeGraphService: graph.json not found at {} — code context disabled", graphPath);
            return;
        }

        try {
            JsonNode root = mapper.readTree(f);
            JsonNode nodes = root.path("nodes");

            Map<String, List<String>> methodsByFile = new HashMap<>();
            List<JsonNode> rawNodes = new ArrayList<>();
            nodes.forEach(rawNodes::add);

            for (JsonNode n : rawNodes) {
                String label = n.path("label").asText("");
                String srcFile = n.path("source_file").asText("");
                if (srcFile.endsWith(".java") && label.startsWith(".")) {
                    String methodName = label.replaceFirst("^\\.", "").replaceAll("\\(.*\\)", "()");
                    methodsByFile.computeIfAbsent(srcFile, k -> new ArrayList<>()).add(methodName);
                }
            }

            for (JsonNode n : rawNodes) {
                String label   = n.path("label").asText("");
                String srcFile = n.path("source_file").asText("");
                if (!srcFile.endsWith(".java")) continue;
                if (!label.endsWith(".java")) continue;

                String module = deriveModule(srcFile);
                List<String> methods = methodsByFile.getOrDefault(srcFile, List.of());
                CodeNode node = new CodeNode(n.path("id").asText(""),
                        label.replace(".java", ""), srcFile, module, methods);
                serviceIndex.computeIfAbsent(module, k -> new ArrayList<>()).add(node);
                classByLabel.put(label.toLowerCase().replace(".java", ""), node);
                indexForFailure(node);
            }

            loaded = true;
            int total = serviceIndex.values().stream().mapToInt(List::size).sum();
            log.info("CodeGraphService: {} classes across {} modules loaded from {}",
                    total, serviceIndex.size(), f.getName());

            buildModuleGraph(root, rawNodes);
        } catch (Exception e) {
            log.warn("CodeGraphService: graph.json load failed — {}", e.getMessage());
        }
    }

    /** Real service-to-service coupling graph, aggregated from every edge in
     * graph.json (not just the class-level nodes deriveModule() indexes) --
     * this is the graph traversal deriveModule/serviceIndex never did. */
    private void buildModuleGraph(JsonNode root, List<JsonNode> rawNodes) {
        Map<String, String> moduleByNodeId = new HashMap<>();
        for (JsonNode n : rawNodes) {
            String srcFile = n.path("source_file").asText("");
            String mod = deriveModule(srcFile);
            if (!"unknown".equals(mod)) moduleByNodeId.put(n.path("id").asText(""), mod);
        }

        int edgesUsed = 0;
        for (JsonNode link : root.path("links")) {
            String relation = link.path("relation").asText("");
            Double weight = RELATION_WEIGHT.get(relation);
            if (weight == null) continue; // containment/method edges excluded entirely

            String srcId = link.path("source").asText(link.path("_src").asText(""));
            String tgtId = link.path("target").asText(link.path("_tgt").asText(""));
            String srcMod = moduleByNodeId.get(srcId);
            String tgtMod = moduleByNodeId.get(tgtId);
            if (srcMod == null || tgtMod == null || srcMod.equals(tgtMod)) continue; // only cross-service edges

            double confidence = link.path("confidence_score").asDouble(0.5);
            double edgeWeight = weight * confidence;
            moduleGraph.computeIfAbsent(srcMod, k -> new LinkedHashMap<>())
                    .merge(tgtMod, edgeWeight, Double::sum);
            edgesUsed++;
        }
        log.info("CodeGraphService: module coupling graph built from {} real cross-service edges across {} services",
                edgesUsed, moduleGraph.size());
    }

    /** Blast radius: weighted multi-hop BFS over the real module coupling
     * graph starting at `rootService`, decaying by 0.5 per hop so a direct
     * caller counts more than a 3-hop-removed one. Returns service -> reach
     * score (0 for rootService itself and anything unreachable).
     */
    public Map<String, Double> computeBlastRadius(String rootService, int maxHops) {
        Map<String, Double> reach = new LinkedHashMap<>();
        Map<String, Double> frontier = new LinkedHashMap<>();
        frontier.put(rootService, 1.0);
        Set<String> visited = new HashSet<>(Set.of(rootService));

        for (int hop = 1; hop <= maxHops; hop++) {
            Map<String, Double> next = new LinkedHashMap<>();
            for (Map.Entry<String, Double> e : frontier.entrySet()) {
                Map<String, Double> outEdges = moduleGraph.getOrDefault(e.getKey(), Map.of());
                for (Map.Entry<String, Double> out : outEdges.entrySet()) {
                    if (visited.contains(out.getKey())) continue;
                    double contribution = e.getValue() * out.getValue() * Math.pow(0.5, hop - 1);
                    next.merge(out.getKey(), contribution, Double::sum);
                    reach.merge(out.getKey(), contribution, Double::sum);
                }
            }
            visited.addAll(next.keySet());
            frontier = next;
            if (frontier.isEmpty()) break;
        }
        return reach;
    }

    /** Real graph-based explanatory scores: for each candidate service, how
     * well does its real multi-hop blast radius (weighted overlap with
     * OTHER services' positive z-score anomalies) structurally explain the
     * observed anomaly pattern? Deliberately returns raw scores, not a
     * ranking -- an earlier version built a full ranking from these scores
     * alone (clipping every negative z-score to 0 first), which threw away
     * the real relative signal CascadeFailureDetector.topologyAdjustedRank
     * exploits directly from raw (often all-negative) z-scores, and a
     * degenerate window (every service pinned at the "-3.333 no-data"
     * sentinel -- common for short 5s fault windows) left every candidate
     * tied at exactly 0.0, silently falling back to Set/List iteration
     * order -- confirmed by a direct test picking a different "winner"
     * than the proven topology method on identical tied input. Now used
     * only as a genuine PROMOTION signal on top of that proven base
     * ranking (see diagnoseByGraphRagForRange), the same pattern the
     * frac-override logic already uses successfully. */
    public Map<String, Double> computeExplanatoryScores(Map<String, Double> zScores) {
        Map<String, Double> scores = new LinkedHashMap<>();
        for (String candidate : DIAGNOSABLE) {
            Map<String, Double> blast = computeBlastRadius(candidate, 3);
            double explanatoryScore = 0.0;
            for (Map.Entry<String, Double> e : zScores.entrySet()) {
                if (e.getKey().equals(candidate)) continue;
                double z = Math.max(0.0, e.getValue()); // only real positive anomalies count as "explained"
                explanatoryScore += blast.getOrDefault(e.getKey(), 0.0) * z;
            }
            scores.put(candidate, explanatoryScore);
        }
        return scores;
    }

    public Map<String, Map<String, Double>> getModuleGraph() {
        return Collections.unmodifiableMap(moduleGraph);
    }

    private void loadBrokerTopology() {
        // Derive topology path from graph path (sibling file)
        String topoPath = graphPath.replace("graph.json", "queue_topology.json");
        File f = new File(topoPath);
        if (!f.exists()) {
            f = new File("/home/admin-/Desktop/EDI6/clearflow/graphify-out/queue_topology.json");
        }
        if (!f.exists()) {
            log.warn("CodeGraphService: queue_topology.json not found — broker context disabled");
            return;
        }

        try {
            JsonNode root = mapper.readTree(f);

            // Load Kafka topics
            root.path("brokers").path("kafka").path("topics").fields().forEachRemaining(e -> {
                QueueNode node = parseQueueNode(e.getKey(), "KAFKA", e.getValue());
                queueIndex.put(e.getKey(), node);
                indexQueueByService(node);
            });

            // Load ActiveMQ queues
            root.path("brokers").path("activemq").path("queues").fields().forEachRemaining(e -> {
                QueueNode node = parseQueueNode(e.getKey(), "ACTIVEMQ", e.getValue());
                queueIndex.put(e.getKey(), node);
                indexQueueByService(node);
            });

            // Load Solace topics
            root.path("brokers").path("solace").path("topics").fields().forEachRemaining(e -> {
                QueueNode node = parseQueueNode(e.getKey(), "SOLACE", e.getValue());
                queueIndex.put(e.getKey(), node);
                indexQueueByService(node);
            });

            // Pipeline flow
            root.path("pipelineFlow").forEach(step -> {
                String s = String.format("Step %d [%s]: %s",
                        step.path("step").asInt(),
                        step.path("service").asText("?"),
                        step.path("action").asText(""));
                pipelineFlow.add(s);
            });

            // Saga flow
            JsonNode saga = root.path("sagaFlow");
            if (!saga.isMissingNode()) {
                StringBuilder sb = new StringBuilder();
                sb.append("Trigger: ").append(saga.path("trigger").asText()).append("\n");
                sb.append("Route: ").append(saga.path("compensationClass").asText()).append("\n");
                saga.path("steps").forEach(s -> sb.append("  ").append(s.asText()).append("\n"));
                sagaFlowSummary = sb.toString();
            }

            // DLQ config
            JsonNode dlq = root.path("dlqConfig");
            if (!dlq.isMissingNode()) {
                dlqConfigSummary = String.format(
                        "maxRetries=%d delay=%s backoff=%s destination=%s",
                        dlq.path("maximumRedeliveries").asInt(3),
                        dlq.path("redeliveryDelayMs").asText("1000ms"),
                        dlq.path("backoff").asText("exponential"),
                        dlq.path("dlqDestination").asText("CLEARFLOW.PAYMENT.DLQ"));
            }

            // Circuit breakers
            root.path("circuitBreakers").forEach(cb -> {
                String name = cb.path("name").asText("");
                String desc = String.format("wraps %s in %s — fallback: %s — opens when: %s",
                        cb.path("wraps").asText("?"),
                        cb.path("file").asText("?"),
                        cb.path("fallback").asText("?"),
                        cb.path("opensWhen").asText("?"));
                circuitBreakerDesc.put(name, desc);
            });

            topologyLoaded = true;
            log.info("CodeGraphService: broker topology loaded — {} queues/topics, {} services indexed",
                    queueIndex.size(), serviceQueueMap.size());

            addBrokerEdgesToModuleGraph();
        } catch (Exception e) {
            log.warn("CodeGraphService: queue_topology.json load failed — {}", e.getMessage());
        }
    }

    /** The real causal blast-radius graph for THIS architecture: this is a
     * message-driven system where services communicate via Kafka/ActiveMQ,
     * not direct Java method calls -- the static code-call graph
     * (buildModuleGraph, above) found real edges from every service to the
     * shared `common` library, but essentially zero real edges BETWEEN the
     * actual business services (settlement's Java doesn't call
     * routing-execution's Java; it produces a message routing-execution's
     * Kafka consumer picks up later). Real broker producer/consumer wiring
     * -- extracted directly from every @KafkaListener/kafkaTemplate.send()
     * call in the codebase into queue_topology.json -- IS the real
     * propagation path: for every topic, every producer service causally
     * affects every consumer service if that topic's messages stop
     * flowing or start failing. Added on top of (not replacing) the code
     * graph's edges, weighted higher since this is the mechanism that
     * actually matches how failures propagate in this system. */
    private void addBrokerEdgesToModuleGraph() {
        int edgesAdded = 0;
        for (QueueNode q : queueIndex.values()) {
            for (String producer : q.producerServices()) {
                if (producer.isBlank()) continue;
                for (String consumer : q.consumerServices()) {
                    if (consumer.isBlank() || consumer.equals(producer)) continue;
                    moduleGraph.computeIfAbsent(producer, k -> new LinkedHashMap<>())
                            .merge(consumer, 1.2, Double::sum); // weighted above the strongest code-graph relation (calls=1.0)
                    edgesAdded++;
                }
            }
        }
        log.info("CodeGraphService: {} real broker producer->consumer edges added to blast-radius graph", edgesAdded);
    }

    private QueueNode parseQueueNode(String name, String broker, JsonNode node) {
        List<String> pSvcs = new ArrayList<>(), pCls = new ArrayList<>(), pFiles = new ArrayList<>();
        List<String> cSvcs = new ArrayList<>(), cCls = new ArrayList<>(), cFiles = new ArrayList<>();

        node.path("producers").forEach(p -> {
            pSvcs.add(p.path("service").asText(""));
            pCls.add(p.path("class").asText(""));
            pFiles.add(p.path("file").asText(""));
        });
        node.path("consumers").forEach(c -> {
            cSvcs.add(c.path("service").asText(""));
            cCls.add(c.path("class").asText(""));
            cFiles.add(c.path("file").asText(""));
        });

        return new QueueNode(name, broker,
                node.path("purpose").asText(""),
                node.path("isDLQ").asBoolean(false),
                node.path("isSagaTrigger").asBoolean(false),
                pSvcs, pCls, pFiles, cSvcs, cCls, cFiles);
    }

    private void indexQueueByService(QueueNode q) {
        q.producerServices().forEach(s -> {
            if (!s.isBlank()) serviceQueueMap.computeIfAbsent(s, k -> new ArrayList<>()).add(q);
        });
        q.consumerServices().forEach(s -> {
            if (!s.isBlank()) serviceQueueMap.computeIfAbsent(s, k -> new ArrayList<>()).add(q);
        });
    }

    /**
     * Returns code context for a given microservice and failure event type.
     * Used by the explainIncidentWithCode MCP tool to inject codebase context
     * into the LLM prompt so it can give file-and-class-level resolution advice.
     *
     * @param service       one of: gateway, validation-enrichment, fraud-scoring,
     *                      aml-compliance, routing-execution, settlement, audit
     * @param failureType   event type or cascade type from ES log:
     *                      CIRCUIT_BREAKER, SAGA_COMPENSATION, AML_SANCTIONS_HIT, etc.
     * @return formatted code context block (fits inside LLM prompt)
     */
    public String getCodeContext(String service, String failureType) {
        if (!loaded) return "(code graph not available)";

        StringBuilder sb = new StringBuilder();

        // 1. Service-specific classes
        List<CodeNode> serviceClasses = serviceIndex.getOrDefault(service, List.of());
        if (!serviceClasses.isEmpty()) {
            sb.append("RELEVANT SOURCE FILES in ").append(service).append(":\n");
            serviceClasses.stream()
                    .sorted(Comparator.comparingInt(n -> -n.methods().size())) // most methods first
                    .limit(6)
                    .forEach(node -> {
                        sb.append("  ").append(node.label())
                          .append(" — ").append(node.sourceFile()).append("\n");
                        if (!node.methods().isEmpty()) {
                            String methodList = node.methods().stream()
                                    .limit(4)
                                    .collect(Collectors.joining(", "));
                            sb.append("    methods: ").append(methodList).append("\n");
                        }
                    });
        }

        // 2. Failure-type-specific classes (cross-service)
        if (failureType != null && !failureType.isBlank()) {
            List<CodeNode> failureClasses = getFailureClasses(failureType);
            if (!failureClasses.isEmpty()) {
                sb.append("\nCLASSES RELATED TO ").append(failureType).append(":\n");
                failureClasses.stream().limit(5).forEach(node -> {
                    sb.append("  ").append(node.label())
                      .append(" [").append(node.module()).append("]")
                      .append(" — ").append(node.sourceFile()).append("\n");
                    if (!node.methods().isEmpty()) {
                        String methodList = node.methods().stream()
                                .limit(3)
                                .collect(Collectors.joining(", "));
                        sb.append("    methods: ").append(methodList).append("\n");
                    }
                });
            }
        }

        return sb.isEmpty() ? "(no code context found for service=" + service + ")" : sb.toString();
    }

    /**
     * Returns broker topology context for a service + cascade type.
     * Appended to the LLM prompt in traceBrokerCascade to give cross-service
     * message flow context so the LLM can explain the propagation path.
     */
    public String getBrokerContext(String service, String cascadeType) {
        if (!topologyLoaded) return "(broker topology not available)";

        StringBuilder sb = new StringBuilder();

        // Queues this service uses
        List<QueueNode> queues = serviceQueueMap.getOrDefault(service, List.of());
        if (!queues.isEmpty()) {
            sb.append("BROKER CHANNELS for ").append(service).append(":\n");
            queues.stream().distinct().forEach(q -> {
                boolean isProducer = q.producerServices().contains(service);
                boolean isConsumer = q.consumerServices().contains(service);
                String role = isProducer && isConsumer ? "PRODUCES+CONSUMES" :
                              isProducer ? "PRODUCES →" : "← CONSUMES";
                sb.append(String.format("  [%s] %s %s (%s)\n",
                        q.broker(), role, q.name(), q.purpose()));
                if (q.isDLQ()) sb.append("    ⚠ THIS IS A DEAD LETTER QUEUE\n");
                if (q.isSagaTrigger()) sb.append("    ⚡ THIS TRIGGERS SAGA COMPENSATION\n");
            });
        }

        // Cascade-type-specific context
        if (cascadeType != null) {
            String upper = cascadeType.toUpperCase();
            sb.append("\n");
            switch (upper) {
                case "CIRCUIT_BREAKER" -> {
                    sb.append("CIRCUIT BREAKER CONFIG:\n");
                    circuitBreakerDesc.forEach((name, desc) ->
                            sb.append("  CB[").append(name).append("]: ").append(desc).append("\n"));
                }
                case "SAGA_COMPENSATION" -> {
                    sb.append("SAGA COMPENSATION FLOW:\n");
                    if (!sagaFlowSummary.isBlank())
                        Arrays.stream(sagaFlowSummary.split("\n"))
                              .forEach(line -> sb.append("  ").append(line).append("\n"));
                }
                case "RETRY_STORM", "QUEUE_OVERFLOW" -> {
                    sb.append("DLQ / RETRY CONFIG:\n  ").append(dlqConfigSummary).append("\n");
                    // Show DLQ queues
                    queueIndex.values().stream().filter(QueueNode::isDLQ).forEach(q ->
                            sb.append("  DLQ: ").append(q.name())
                              .append(" [").append(q.broker()).append("] — ").append(q.purpose()).append("\n"));
                }
                case "DOWNSTREAM_STARVATION" -> {
                    sb.append("PIPELINE FLOW (starvation propagation path):\n");
                    pipelineFlow.forEach(step -> sb.append("  ").append(step).append("\n"));
                }
            }
        }

        return sb.isEmpty() ? "(no broker context for service=" + service + ")" : sb.toString();
    }

    /**
     * Returns the full payment pipeline as an ASCII flow diagram.
     * Used in traceBrokerCascade to show the complete broker hop chain.
     */
    public String getFullPipelineTopology() {
        if (!topologyLoaded) return "(topology not loaded)";

        StringBuilder sb = new StringBuilder();
        sb.append("CLEARFLOW PAYMENT PIPELINE — 3-BROKER TOPOLOGY\n");
        sb.append("─".repeat(60)).append("\n");
        sb.append("[Kafka]  gateway.KafkaEventPublisher\n");
        sb.append("  → clearflow.payment.initiated\n");
        sb.append("     ├─ fraud-scoring.FraudKafkaConsumer (parallel)\n");
        sb.append("     └─ audit.AuditEventConsumer (fan-out)\n\n");
        sb.append("[ActiveMQ/Camel]  Orchestration backbone:\n");
        sb.append("  gateway.ActiveMQPublisher\n");
        sb.append("  → CLEARFLOW.PAYMENT.INITIATED\n");
        sb.append("     └─ validation-enrichment.ValidationEnrichmentCamelRoute\n");
        sb.append("          → CLEARFLOW.PAYMENT.VALIDATED\n");
        sb.append("               └─ aml-compliance.AMLCamelRoute\n");
        sb.append("                    ├─ [HIT]  CLEARFLOW.PAYMENT.SANCTIONS.HIT (terminal)\n");
        sb.append("                    └─ [CLEAR] CLEARFLOW.PAYMENT.SANCTIONS.CLEAR\n");
        sb.append("                               └─ routing-execution.RoutingCamelRoute\n");
        sb.append("                                    → CLEARFLOW.PAYMENT.ROUTED\n");
        sb.append("                                         └─ settlement.SettlementCamelRoute\n");
        sb.append("                                              ├─ [OK]   clearflow.payment.settled\n");
        sb.append("                                              └─ [FAIL] CLEARFLOW.PAYMENT.SETTLEMENT.FAILED\n");
        sb.append("                                                          └─ SagaCompensationRoute ← SAGA\n\n");
        sb.append("[DLQ]  All Camel routes → CLEARFLOW.PAYMENT.DLQ (3 retries, exp backoff)\n");
        sb.append("[CB]   gateway: CB[KAFKA]→CB[ACTIVEMQ]→CB[SOLACE] (Resilience4j fallback chain)\n");

        return sb.toString();
    }

    /**
     * Returns a compact summary of which services have how many indexed classes.
     * Used by the MCP tool to report graph coverage.
     */
    public Map<String, Integer> getCoverage() {
        Map<String, Integer> coverage = new LinkedHashMap<>();
        serviceIndex.forEach((svc, cls) -> coverage.put(svc, cls.size()));
        return coverage;
    }

    public boolean isLoaded() { return loaded; }
    public boolean isTopologyLoaded() { return topologyLoaded; }
    public Map<String, QueueNode> getQueueIndex() { return Collections.unmodifiableMap(queueIndex); }

    // ── Private helpers ───────────────────────────────────────────────────────

    private static final Set<String> KNOWN_MODULES = Set.of(
            "gateway", "fraud-scoring", "validation-enrichment", "aml-compliance",
            "routing-execution", "settlement", "audit", "mcp-readonly-gateway",
            "common", "config-server");

    /** graph.json's source_file is a MIX of relative ("gateway/src/...") and
     * absolute ("/home/admin-/Desktop/EDI6/clearflow/gateway/src/...")
     * paths (1015 absolute, 144 relative for .java nodes alone, confirmed
     * by direct inspection) -- the original version of this method assumed
     * relative-only and returned "unknown" for every absolute path, which
     * is most of them, silently collapsing almost the entire real code
     * graph into one bucket. Fixed to find the known module-directory
     * segment wherever it falls in the path, not just at index 0. */
    private String deriveModule(String sourceFile) {
        String[] parts = sourceFile.split("/");
        for (String part : parts) {
            if (KNOWN_MODULES.contains(part)) return part;
        }
        return "unknown";
    }

    private void indexForFailure(CodeNode node) {
        String combined = (node.label() + " " + String.join(" ", node.methods())).toLowerCase();
        for (Map.Entry<String, String[]> entry : FAILURE_KEYWORDS.entrySet()) {
            for (String keyword : entry.getValue()) {
                if (combined.contains(keyword.toLowerCase())) {
                    failureIndex.computeIfAbsent(entry.getKey(), k -> new ArrayList<>()).add(node);
                    break;
                }
            }
        }
    }

    private List<CodeNode> getFailureClasses(String failureType) {
        String upper = failureType.toUpperCase();
        // Direct match first
        if (failureIndex.containsKey(upper)) return failureIndex.get(upper);

        // Fuzzy match — find the key whose keywords overlap most with failureType tokens
        String[] tokens = upper.split("[_\\s]+");
        return failureIndex.entrySet().stream()
                .filter(e -> Arrays.stream(tokens).anyMatch(t -> e.getKey().contains(t) || t.contains(e.getKey())))
                .flatMap(e -> e.getValue().stream())
                .distinct()
                .limit(5)
                .collect(Collectors.toList());
    }

    /**
     * Maps failure categories to class-name keywords.
     * These drive which graph nodes surface for a given failure type.
     */
    private static final Map<String, String[]> FAILURE_KEYWORDS = new LinkedHashMap<>() {{
        put("CIRCUIT_BREAKER",      new String[]{"CircuitBreaker","Resilience","Fallback","Retry"});
        put("RETRY_STORM",          new String[]{"Retry","RetryTemplate","RetryPolicy","Backoff"});
        put("SAGA_COMPENSATION",    new String[]{"Saga","Compensation","Rollback","Revert","Undo"});
        put("DOWNSTREAM_STARVATION",new String[]{"ConnectionPool","DataSource","Pool","Starvation","Backpressure"});
        put("AML_SANCTIONS_HIT",    new String[]{"AML","Screening","Sanction","SDN","Fuzzy","PEP"});
        put("FRAUD",                new String[]{"Fraud","Risk","Score","Scoring","Detector","FraudPattern"});
        put("SETTLEMENT",           new String[]{"Settlement","Settle","Nostro","RTGS","Rails"});
        put("ROUTING",              new String[]{"Routing","Router","Rail","RailSelector","Execution"});
        put("VALIDATION",           new String[]{"Validation","Validator","Enrichment","IBAN","BIC","Schema"});
        put("EMBARGO",              new String[]{"Embargo","Country","Sanction","Blocked","Compliance"});
        put("TIMEOUT",              new String[]{"Timeout","TimedOut","Async","Async","Deadline"});
        put("QUEUE_OVERFLOW",       new String[]{"Queue","DLQ","DeadLetter","Overflow","Backlog"});
    }};
}
