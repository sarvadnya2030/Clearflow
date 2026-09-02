# Graph Report - /home/admin-/Desktop/EDI6/clearflow  (2026-08-25)

## Corpus Check
- Large corpus: 300 files · ~179,480 words. Semantic extraction will be expensive (many Claude tokens). Consider running on a subfolder, or use --no-semantic to run AST-only.

## Summary
- 1894 nodes · 2467 edges · 135 communities detected
- Extraction: 78% EXTRACTED · 21% INFERRED · 0% AMBIGUOUS · INFERRED: 530 edges (avg confidence: 0.53)
- Token cost: 0 input · 0 output

## God Nodes (most connected - your core abstractions)
1. `ScreeningRecord` - 43 edges
2. `SettlementRecord` - 27 edges
3. `ValidationRecord` - 25 edges
4. `ClearFlowMcpTools` - 25 edges
5. `ElasticsearchLogFetcher` - 24 edges
6. `PaymentEnrichment` - 23 edges
7. `AuditRecord` - 21 edges
8. `LedgerEntry` - 21 edges
9. `_build_payload()` - 17 edges
10. `SimulatorConfig` - 17 edges

## Surprising Connections (you probably didn't know these)
- `ClearFlow Demo Ready to Run (4-tab, LightGBM fix)` --semantically_similar_to--> `ClearFlow Complete Demo (6 tabs, 2026-05-22)`  [INFERRED] [semantically similar]
  DEMO_READY.md → DEMO_READY_FINAL.md
- `ClearFlow Observability Demo — Full Stack Guide` --semantically_similar_to--> `Live Demo Structure (8-phase, 15-20 min)`  [INFERRED] [semantically similar]
  OBSERVABILITY_DEMO_GUIDE.md → DEMO_STRUCTURE.md
- `FuzzyScreeningEngine v3 (Levenshtein + phonetic)` --semantically_similar_to--> `Jaro-Winkler over Levenshtein Rationale`  [INFERRED] [semantically similar]
  compliance-reports/OFAC_Screening_20260416_041247.txt → docs/ARCHITECTURE.md
- `Failure Classification Table` --semantically_similar_to--> `ClearFlow-RCA Fault Taxonomy (Module 2)`  [INFERRED] [semantically similar]
  diagnostic-agents/README.md → data-generation/fault_taxonomy.md
- `FinCEN SAR Filing Requirement` --semantically_similar_to--> `classifyRootCause MCP tool`  [INFERRED] [semantically similar]
  compliance-reports/SAR_20260416_041247_summary.txt → evaluation-artifacts/mcp-tier4-evaluation.md

## Hyperedges (group relationships)
- **100K Cascading Failure Investigation (multi-doc)** — t100kfail_cascading_failure_report, paysuccess_analysis, obsdemosum_100k_demo_summary, elkmcpgraphify_integration_doc, dashguide_streamlit_dashboard, cascadedemo_root_cause_batch40 [INFERRED 0.85]
- **Roadmap Phase 1 Stop-the-Bleeding Fix Set** — roadmap_task11_outbox_dlq, roadmap_task12_audit_errorloop, roadmap_task13_logback_rolling, sess_publishfallback_silent_drop, sess_audit_kafka_error_loop, sess_disk_full_kafka_crash [INFERRED 0.80]
- **MCP Cascade Detection Ecosystem** — mcpprod_cascade_failure_detector, mcpprod_cascade_monitoring_service, mcpevalfinal_detect_cascade_tool, mcpevalfinal_get_recent_cascades_tool, phase4_cascade_alerting_service, phase4_predictive_simulator [EXTRACTED 0.90]
- **OFAC/EU-AMLD6/FATF Regulatory Reference Triad Feeding AML Compliance** — ofacpolicy_doc, eu_amld6_doc, fatf_recommendations_doc, overview_aml_fraud, fuzzy_screening_engine [INFERRED 0.75]
- **ClearFlow-RCA Dataset Generation Pipeline (Modules 1-9)** — datagen_build_script, datagen_inject_incidents_py, datagen_eval_harness_py, datagen_graph_builder_py, incidents_schema_template, graphschema_doc, faulttax_doc [EXTRACTED 0.90]
- **ELK + MCP + Graphify Combined Observability Demo** — summary_elk_stack, summary_mcp_gateway_integration, summary_graphify_architecture, summary_streamlit_dashboard, summary_root_cause_analysis [EXTRACTED 0.90]
- **Compliance filing run at 04:12:47 (CTR + LCR + SAR)** — ctr041247_report, lcr041247_report, sar041247_report [EXTRACTED 1.00]
- **MCP Tier 4 tool evaluation trio via MCP Gateway** — mcptier4_getpaymenttimeline, mcptier4_classifyrootcause, mcptier4_explainincidentwithcode, mcptier4_mcp_gateway [EXTRACTED 0.90]
- **Knowledge graph artifact referenced across evaluation docs (node/edge counts inconsistent)** — finalresults_knowledge_graph, collectionmanifest_graphifyout, graphreport_doc [INFERRED 0.75]

## Communities

### Community 0 - "AccessLogService (MCP audit logging)"
Cohesion: 0.02
Nodes (20): AccessLogService, AMLKafkaConsumer, DlqPublisher, FraudKafkaConsumerIT, IntegrationTestBase, KafkaTopics, LiquidityReleaseConsumer, LiquidityReservationProcessor (+12 more)

### Community 1 - "ActiveMQPublisher (JMS integration)"
Cohesion: 0.03
Nodes (17): ActiveMQPublisher, AMLPatternInjector, CircuitBreakerNames, DemoDataLoader, IdempotencyService, KafkaEventPublisher, MaskedIbanSerializer, PaymentController (+9 more)

### Community 2 - "Demo/Eval Status Docs"
Cohesion: 0.03
Nodes (86): ClearFlow Demo Ready to Run (4-tab, LightGBM fix), Fix: Recalibrated heuristic fraud scorer, disabled broken LightGBM, wait-and-finalize.sh / finalize-evaluation.sh, Evaluation Status — Live Tracking (Batch 168/200), Data Visibility Verification Matrix, Observability Visibility Checklist for Demos, Observability Data Flow Architecture Diagram, ClearFlow Observability Demo — Full Stack Guide (+78 more)

### Community 3 - "MCP Gateway Tools & Services"
Cohesion: 0.03
Nodes (13): LLMClient, McpMetricsService, McpRateLimiter, State, MCPTool, McpToolsConfig, PaymentTimelineReconstructor, PaymentTimelineTool (+5 more)

### Community 4 - "Architecture Doc & Design Rationale"
Cohesion: 0.03
Nodes (80): AI / MCP Layer Architecture, Design Rationale Section (§16), ClearFlow System Architecture Document, Jaro-Winkler over Levenshtein Rationale, Observability Stack (Prometheus/Grafana/Jaeger/ELK), Payment Lifecycle End-to-End, Rail Selection Logic (§5), Rationale: Why Apache Camel (+72 more)

### Community 5 - "Evaluation Artifacts Collection"
Cohesion: 0.03
Nodes (78): ClearFlow Evaluation Artifacts Collection Manifest, 7 Grafana dashboard definitions, graphify-out/ (1,162 nodes, 1,471 edges), mcp-outputs/, batch_100k.py load test, ClearFlow Evaluation Summary, MCP endpoint access blocker (HTTP 404), Tier 1 — Essential Artifacts (+70 more)

### Community 6 - "ClickHouseAnalyticsService"
Cohesion: 0.04
Nodes (9): ClickHouseAnalyticsService, DoubleEntryAccountingTest, LedgerEntry, LedgerRepository, SettlementController, SettlementKafkaConsumer, SettlementProcessor, SettlementRepository (+1 more)

### Community 7 - "AuditController (hash-chain audit)"
Cohesion: 0.04
Nodes (7): AuditController, AuditEventConsumer, AuditRecord, AuditRecordKey, AuditRepository, HashChainIntegrityTest, HashChainService

### Community 8 - "Cascade Root-Cause Analysis Docs"
Cohesion: 0.05
Nodes (54): Root Cause: Gateway JVM heap exhaustion, Fix: Heap 1GB->2GB + G1GC, Monitoring Gaps, Cascade Root Cause Analysis — Batch 40 Gateway Crash, Cascade Analyzer Run Output, AdminController.java, CascadeSimulation.jsx, Demo Context Transfer Doc (2026-05-22) (+46 more)

### Community 9 - "CountryRiskMatrix (AML risk scoring)"
Cohesion: 0.05
Nodes (9): CountryRiskMatrix, FeatureEngineeringService, FraudKafkaConsumer, FraudScoringController, FraudScoringService, FraudScoringServiceTest, HeuristicScoringService, LightGBMStubClient (+1 more)

### Community 10 - "PaymentRail Enum & Rail Selection"
Cohesion: 0.06
Nodes (5): PaymentRailRule, RailRules, RailSelectionEngine, RailSelectionProcessor, RailSelectionTest

### Community 11 - "Diagnostic Agents (Claude-based)"
Cohesion: 0.05
Nodes (30): BaseAgent, Base agent with Claude API integration and MCP tool calling., Base class for diagnostic agents using Claude with tool use., Build tool definitions that map to MCP gateway endpoints., Call MCP gateway endpoint and return JSON result., Run Claude with tool use loop until completion., AgentRunner, Orchestrator for diagnostic agents. (+22 more)

### Community 12 - "ScreeningRecord (AML domain model)"
Cohesion: 0.05
Nodes (1): ScreeningRecord

### Community 13 - "AMLScreeningProcessor (AML-hold gate)"
Cohesion: 0.07
Nodes (6): AMLScreeningProcessor, ComplianceReviewController, FuzzyMatchTest, FuzzyScreeningEngine, ScreeningRecordRepository, SDNLoader

### Community 14 - "ComplianceTool (MCP compliance tool)"
Cohesion: 0.09
Nodes (3): ComplianceTool, ElasticsearchLogFetcher, FraudScoreTool

### Community 15 - "OFAC/SAR/AMLD6/FATF Compliance Docs"
Cohesion: 0.08
Nodes (37): OFAC Screening Summary Report 041247 (100K txns, 30 hits), OFAC Screening Summary Report 042246 (77,027 txns, 500 hits), SAR Filing Summary 042246 (500 SARs), Article 3 — ML Offences & 22 Predicate Offences, Article 6 — Criminal Liability of Legal Persons, Article 7 — Sanctions for Legal Persons, Beneficial Ownership Register, Correspondent Banking Enhanced Due Diligence (EU) (+29 more)

### Community 16 - "EnrichmentProcessor (validation)"
Cohesion: 0.07
Nodes (3): EnrichmentProcessor, PaymentEnrichment, PaymentEnrichmentRepository

### Community 17 - "CascadeDetectionController"
Cohesion: 0.09
Nodes (3): CascadeDetectionController, CascadeFailureDetector, CascadeMonitoringService

### Community 18 - "ValidationRecord (validation domain)"
Cohesion: 0.07
Nodes (2): ValidationRecord, ValidationRecordRepository

### Community 19 - "SettlementRecord (settlement domain)"
Cohesion: 0.07
Nodes (1): SettlementRecord

### Community 20 - "generate_paysim_iso.py (legacy generator)"
Cohesion: 0.16
Nodes (23): _balances_fraud(), _balances_normal(), _bic(), _build_payload(), _city(), _company(), _gen_account_takeover(), _gen_embargoed_transit() (+15 more)

### Community 21 - "ClearFlowMcpTools (cascade detection)"
Cohesion: 0.12
Nodes (1): ClearFlowMcpTools

### Community 22 - "observability_dashboard.py (Streamlit)"
Cohesion: 0.14
Nodes (15): _es(), es_summary(), fraud_geo(), get_forecast(), get_uetr_anomalies(), _mcp(), mcp_fraud(), mcp_overview() (+7 more)

### Community 23 - "extract_queue_topology.py"
Cohesion: 0.19
Nodes (20): _build_service_index(), build_topology(), collect_activemq_consumers(), collect_activemq_producers(), collect_kafka_consumers(), collect_kafka_producers(), derive_class(), derive_service() (+12 more)

### Community 24 - "Fraud Model Server (LightGBM)"
Cohesion: 0.16
Nodes (16): BaseModel, engineer_features(), health(), HealthResponse, load_or_train_model(), predict(), PredictRequest, PredictResponse (+8 more)

### Community 25 - "SimulatorConfig (load simulator)"
Cohesion: 0.11
Nodes (1): SimulatorConfig

### Community 26 - "clearflow.js (frontend API client)"
Cohesion: 0.23
Nodes (17): cacheRead(), cacheWrite(), fetchAlerts(), fetchCached(), fetchChat(), fetchExplain(), fetchFraudMetrics(), fetchOverview() (+9 more)

### Community 27 - "CodeGraphService (code graph builder)"
Cohesion: 0.17
Nodes (1): CodeGraphService

### Community 28 - "DemoScenarioSeeder"
Cohesion: 0.25
Nodes (1): DemoScenarioSeeder

### Community 29 - "MCPController (chat/alerts endpoints)"
Cohesion: 0.21
Nodes (1): MCPController

### Community 30 - "RootCauseClassifierTest (/)"
Cohesion: 0.29
Nodes (1): RootCauseClassifierTest

### Community 31 - "PredictiveCascadeSimulator (/)"
Cohesion: 0.17
Nodes (2): PredictiveCascadeSimulator, PredictiveController

### Community 32 - "RootCauseClassifier (/)"
Cohesion: 0.35
Nodes (1): RootCauseClassifier

### Community 33 - "pipeline_ingest (/)"
Cohesion: 0.23
Nodes (12): alert_level(), cascade_events(), es_bulk_index(), es_index_for(), generate_transaction(), main(), _normal_amount(), pipeline_events() (+4 more)

### Community 34 - "build_clearflow_rca_dataset (data-generation)"
Cohesion: 0.27
Nodes (13): build_events(), build_payment(), clone_as_duplicate(), derive_aml_state(), derive_payment_state(), main(), make_accounts(), pick_creditor() (+5 more)

### Community 35 - "compliance_reporter (/)"
Cohesion: 0.33
Nodes (11): es_count(), es_search(), generate_ctr(), generate_lcr(), generate_ofac_summary(), generate_sar(), main(), _ofac_program() (+3 more)

### Community 36 - "eval_harness (data-generation)"
Cohesion: 0.23
Nodes (12): graph_topology_baseline(), load(), loudest_metric_baseline(), main(), payment_aware_rca(), print_report(), G0-G3. Starts from graph_topology_baseline's ranking, then reads the     STATE S, Shared helper: error_rate z-score per service during the incident     window vs. (+4 more)

### Community 37 - "inject_incidents (data-generation)"
Cohesion: 0.28
Nodes (12): apply_fault_to_payment(), derive_payment_state(), find_free_window(), gen_metrics_baseline(), main(), parse_dt(), Flat baseline telemetry for every service across the whole window,     5-minute, Rewrites one affected payment's downstream state + appends a     fault-caused ev (+4 more)

### Community 38 - "batch_100k (/)"
Cohesion: 0.2
Nodes (7): build(), get_metric(), kafka_group_lag(), Read a counter from the Prometheus scrape endpoint., Return total consumer lag for a consumer group, or -1 on error., send(), wait_for_drain()

### Community 39 - "FraudPatternInjector (/)"
Cohesion: 0.29
Nodes (1): FraudPatternInjector

### Community 40 - "PaymentTimelineReconstructorTest (/)"
Cohesion: 0.27
Nodes (1): PaymentTimelineReconstructorTest

### Community 41 - "ForecastSettlementService (/)"
Cohesion: 0.32
Nodes (1): ForecastSettlementService

### Community 42 - "batch_realistic_v4 (/)"
Cohesion: 0.31
Nodes (7): build(), get_token(), localStorage_token(), make_remittance(), realistic_amount(), send(), weighted_choice()

### Community 43 - "TransactionPatternLibrary (/)"
Cohesion: 0.33
Nodes (1): TransactionPatternLibrary

### Community 44 - "CascadeAlertingService (/)"
Cohesion: 0.33
Nodes (1): CascadeAlertingService

### Community 45 - "App (frontend)"
Cohesion: 0.29
Nodes (5): AlertRow(), Dashboard(), fmt(), fmtTs(), seedFromCache()

### Community 46 - "PaymentFlowFixed (frontend)"
Cohesion: 0.22
Nodes (2): buildPayload(), uuid()

### Community 47 - "full_test_100k (/)"
Cohesion: 0.39
Nodes (8): build_payload(), main(), _party(), percentile(), print_progress(), run_health_check(), run_mcp_sample(), send_one()

### Community 48 - "graph_builder (data-generation)"
Cohesion: 0.39
Nodes (8): build_full_graph(), extract_tier(), main(), parse_dt(), Returns the subgraph a method at evidence tier `tier` is allowed to     see: onl, Hard assertions: no G-tier may ever contain an Incident node or a     ground-tru, read_csv(), verify_no_leak()

### Community 49 - "cascade_failure_analyzer (/)"
Cohesion: 0.36
Nodes (7): analyze_cascade(), get_test_logs(), main(), Use Claude to analyze cascading failures, Read architecture graph from graphify report, Collect logs from all services, read_graphify()

### Community 50 - "live_payment_sender (/)"
Cohesion: 0.64
Nodes (7): batch_mode(), demo_mode(), health_check(), main(), print_health(), random_payment(), send()

### Community 51 - "PaymentArchTest (/)"
Cohesion: 0.25
Nodes (1): PaymentArchTest

### Community 52 - "AgentRegistry (/)"
Cohesion: 0.36
Nodes (1): AgentRegistry

### Community 53 - "analyze_test_results (/)"
Cohesion: 0.29
Nodes (6): count_elasticsearch_logs(), parse_test_output(), print_report(), Parse batch_100k.py output., Print formatted test report., Count logs in Elasticsearch clearflow-* indices.

### Community 54 - "ProblemDetailBuilder (/)"
Cohesion: 0.29
Nodes (2): GlobalExceptionHandler, ProblemDetailBuilder

### Community 55 - "UETRTrackerController (/)"
Cohesion: 0.48
Nodes (1): UETRTrackerController

### Community 56 - "IbanGeneratorUtil (/)"
Cohesion: 0.43
Nodes (1): IbanGeneratorUtil

### Community 57 - "AdminController (mcp-readonly-gateway)"
Cohesion: 0.43
Nodes (1): AdminController

### Community 58 - "SettlementKafkaConfig (/)"
Cohesion: 0.43
Nodes (1): SettlementKafkaConfig

### Community 59 - "FraudKafkaConfig (/)"
Cohesion: 0.4
Nodes (1): FraudKafkaConfig

### Community 60 - "generate_payments (/)"
Cohesion: 0.6
Nodes (5): generate_iban(), generate_jwt(), generate_payment(), main(), send_payment()

### Community 61 - "ValidationKafkaConfig (/)"
Cohesion: 0.47
Nodes (1): ValidationKafkaConfig

### Community 62 - "FallbackLLMClient (mcp-readonly-gateway)"
Cohesion: 0.47
Nodes (1): FallbackLLMClient

### Community 63 - "RoutingKafkaConfig (/)"
Cohesion: 0.47
Nodes (1): RoutingKafkaConfig

### Community 64 - "CascadeSimulation (frontend)"
Cohesion: 0.4
Nodes (2): buildPayload(), uuid()

### Community 65 - "EnhancedDashboard (frontend)"
Cohesion: 0.33
Nodes (0): 

### Community 66 - "AMLKafkaConfig (/)"
Cohesion: 0.47
Nodes (1): AMLKafkaConfig

### Community 67 - "payment_load_test (/)"
Cohesion: 0.47
Nodes (3): buildPayload(), randomAmount(), randomParty()

### Community 68 - "batch_100k_v3 (/)"
Cohesion: 0.5
Nodes (2): build(), send()

### Community 69 - "batch_100k_realistic (/)"
Cohesion: 0.5
Nodes (2): build_payload(), send()

### Community 70 - "batch_100k_v2 (/)"
Cohesion: 0.5
Nodes (2): build(), send()

### Community 71 - "SecurityConfig (/)"
Cohesion: 0.5
Nodes (1): SecurityConfig

### Community 72 - "GatewayKafkaProducerConfig (/)"
Cohesion: 0.5
Nodes (1): GatewayKafkaProducerConfig

### Community 73 - "NvidiaLLMClient (/)"
Cohesion: 0.4
Nodes (1): NvidiaLLMClient

### Community 74 - "OpenRouterLLMClient (/)"
Cohesion: 0.4
Nodes (1): OpenRouterLLMClient

### Community 75 - "OllamaLLMClient (/)"
Cohesion: 0.4
Nodes (1): OllamaLLMClient

### Community 76 - "MCPSecurityConfig (mcp-readonly-gateway)"
Cohesion: 0.5
Nodes (1): MCPSecurityConfig

### Community 77 - "MetricsTool (/)"
Cohesion: 0.5
Nodes (1): MetricsTool

### Community 78 - "LiveLogViewer (frontend)"
Cohesion: 0.5
Nodes (2): extractService(), LogEntry()

### Community 79 - "PaymentSearch (/)"
Cohesion: 0.4
Nodes (0): 

### Community 80 - "DEMO_STATUS (DEMO_STATUS.md)"
Cohesion: 0.4
Nodes (5): CascadeSimulation.jsx, CONTEXT_TRANSFER.md, EnhancedDashboard.jsx (Real-Time Dashboard), LiveLogViewer.jsx, ClearFlow Demo Build Status (2026-05-22)

### Community 81 - "bulk_sender (/)"
Cohesion: 0.67
Nodes (2): make_payment(), send_one()

### Community 82 - "GatewayKafkaConsumerConfig (/)"
Cohesion: 0.67
Nodes (1): GatewayKafkaConsumerConfig

### Community 83 - "IBANValidationProcessor (/)"
Cohesion: 0.5
Nodes (1): IBANValidationProcessor

### Community 84 - "CurrencyValidationProcessor (/)"
Cohesion: 0.5
Nodes (1): CurrencyValidationProcessor

### Community 85 - "BICValidationProcessor (/)"
Cohesion: 0.5
Nodes (1): BICValidationProcessor

### Community 86 - "EmbargoPreCheckProcessor (/)"
Cohesion: 0.5
Nodes (1): EmbargoPreCheckProcessor

### Community 87 - "EmbargoDataLoader (/)"
Cohesion: 0.5
Nodes (1): EmbargoDataLoader

### Community 88 - "main (/)"
Cohesion: 0.5
Nodes (1): ErrorBoundary

### Community 89 - "train (/)"
Cohesion: 0.83
Nodes (3): country_risk_norm(), currency_risk_norm(), generate_sample()

### Community 90 - "CTR_20260416_041247_summary (compliance-reports)"
Cohesion: 0.83
Nodes (4): Bank Secrecy Act 31 U.S.C. § 5313, FinCEN Form 104, CTR Filing Summary (04:12:47), CTR Filing Summary (04:22:46)

### Community 91 - "batch_10k (/)"
Cohesion: 0.67
Nodes (0): 

### Community 92 - "batch_1k (/)"
Cohesion: 0.67
Nodes (0): 

### Community 93 - "CorrelationIdFilter (/)"
Cohesion: 0.67
Nodes (1): CorrelationIdFilter

### Community 94 - "PiiMaskingConverter (/)"
Cohesion: 0.67
Nodes (1): PiiMaskingConverter

### Community 95 - "MetricsConstants (/)"
Cohesion: 0.67
Nodes (1): MetricsConstants

### Community 96 - "DuplicatePaymentException (/)"
Cohesion: 0.67
Nodes (1): DuplicatePaymentException

### Community 97 - "PaymentException (/)"
Cohesion: 0.67
Nodes (1): PaymentException

### Community 98 - "GatewayApplication (/)"
Cohesion: 0.67
Nodes (1): GatewayApplication

### Community 99 - "IbanValidator (/)"
Cohesion: 0.67
Nodes (1): IbanValidator

### Community 100 - "DevSecurityConfig (/)"
Cohesion: 0.67
Nodes (1): DevSecurityConfig

### Community 101 - "FraudScoringApplication (/)"
Cohesion: 0.67
Nodes (1): FraudScoringApplication

### Community 102 - "ValidationEnrichmentApplication (/)"
Cohesion: 0.67
Nodes (1): ValidationEnrichmentApplication

### Community 103 - "ValidationEnrichmentCamelRoute (/)"
Cohesion: 0.67
Nodes (1): ValidationEnrichmentCamelRoute

### Community 104 - "CamelKafkaConfig (/)"
Cohesion: 0.67
Nodes (1): CamelKafkaConfig

### Community 105 - "ConfigServerApplication (/)"
Cohesion: 0.67
Nodes (1): ConfigServerApplication

### Community 106 - "McpReadonlyGatewayApplication (/)"
Cohesion: 0.67
Nodes (1): McpReadonlyGatewayApplication

### Community 107 - "LLMConfig (mcp-readonly-gateway)"
Cohesion: 0.67
Nodes (1): LLMConfig

### Community 108 - "JwtScopeConverter (/)"
Cohesion: 0.67
Nodes (1): JwtScopeConverter

### Community 109 - "AuditApplication (/)"
Cohesion: 0.67
Nodes (1): AuditApplication

### Community 110 - "CassandraConfig (/)"
Cohesion: 0.67
Nodes (1): CassandraConfig

### Community 111 - "AuditKafkaErrorHandler (/)"
Cohesion: 0.67
Nodes (1): AuditKafkaErrorHandler

### Community 112 - "AuditKafkaConfig (/)"
Cohesion: 0.67
Nodes (1): AuditKafkaConfig

### Community 113 - "RoutingExecutionApplication (/)"
Cohesion: 0.67
Nodes (1): RoutingExecutionApplication

### Community 114 - "RoutingCamelRoute (/)"
Cohesion: 0.67
Nodes (1): RoutingCamelRoute

### Community 115 - "InsufficientLiquidityException (/)"
Cohesion: 0.67
Nodes (1): InsufficientLiquidityException

### Community 116 - "Chat (/)"
Cohesion: 0.67
Nodes (0): 

### Community 117 - "AmlComplianceApplication (/)"
Cohesion: 0.67
Nodes (1): AmlComplianceApplication

### Community 118 - "AMLCamelRoute (/)"
Cohesion: 0.67
Nodes (1): AMLCamelRoute

### Community 119 - "SettlementApplication (/)"
Cohesion: 0.67
Nodes (1): SettlementApplication

### Community 120 - "SettlementCamelRoute (/)"
Cohesion: 0.67
Nodes (1): SettlementCamelRoute

### Community 121 - "SettlementFinalityViolationException (settlement)"
Cohesion: 0.67
Nodes (1): SettlementFinalityViolationException

### Community 122 - "RUN-TEST-GUIDE (RUN-TEST-GUIDE.md)"
Cohesion: 0.67
Nodes (3): demo.sh, Run & Functional Test Guide, test-functionality.sh

### Community 123 - "PaymentFlow (/)"
Cohesion: 1.0
Nodes (0): 

### Community 124 - "GraphifyViewer (/)"
Cohesion: 1.0
Nodes (0): 

### Community 125 - "NavBar (frontend)"
Cohesion: 1.0
Nodes (0): 

### Community 126 - "DashboardTabs (/)"
Cohesion: 1.0
Nodes (0): 

### Community 127 - "README (README.md)"
Cohesion: 1.0
Nodes (2): ClearFlow README Overview, ClearFlow Payment Platform

### Community 128 - "Iban.java"
Cohesion: 1.0
Nodes (0): 

### Community 129 - "PaymentChannel.java"
Cohesion: 1.0
Nodes (0): 

### Community 130 - "UETRTrackingResponse.java"
Cohesion: 1.0
Nodes (0): 

### Community 131 - "vite.config.js"
Cohesion: 1.0
Nodes (0): 

### Community 132 - "Demo Script Test"
Cohesion: 1.0
Nodes (1): Demo Script Test

### Community 133 - "Community 0 — gateway module"
Cohesion: 1.0
Nodes (1): Community 0 — gateway module

### Community 134 - "Community 4 — fraud-scoring module"
Cohesion: 1.0
Nodes (1): Community 4 — fraud-scoring module

## Ambiguous Edges - Review These
- `MCP Gateway & AI Layer Description` → `v1 Idempotency Key Bug Fix Rationale`  [AMBIGUOUS]
  data-generation/README.md · relation: references
- `Knowledge graph (1,162 nodes, 94 communities)` → `Graph Report (GRAPH_REPORT.md)`  [AMBIGUOUS]
  evaluation-artifacts/graphify-out/GRAPH_REPORT.md · relation: references

## Knowledge Gaps
- **177 isolated node(s):** `Read a counter from the Prometheus scrape endpoint.`, `Return total consumer lag for a consumer group, or -1 on error.`, `Read architecture graph from graphify report`, `Collect logs from all services`, `Use Claude to analyze cascading failures` (+172 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `PaymentFlow (/)`** (2 nodes): `PaymentFlow.jsx`, `PaymentFlow()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `GraphifyViewer (/)`** (2 nodes): `GraphifyViewer.jsx`, `GraphifyViewer()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `NavBar (frontend)`** (2 nodes): `NavBar.jsx`, `NavBar()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `DashboardTabs (/)`** (2 nodes): `DashboardTabs.jsx`, `DashboardTabs()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `README (README.md)`** (2 nodes): `ClearFlow README Overview`, `ClearFlow Payment Platform`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Iban.java`** (1 nodes): `Iban.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `PaymentChannel.java`** (1 nodes): `PaymentChannel.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `UETRTrackingResponse.java`** (1 nodes): `UETRTrackingResponse.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `vite.config.js`** (1 nodes): `vite.config.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Demo Script Test`** (1 nodes): `Demo Script Test`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 0 — gateway module`** (1 nodes): `Community 0 — gateway module`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 4 — fraud-scoring module`** (1 nodes): `Community 4 — fraud-scoring module`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `MCP Gateway & AI Layer Description` and `v1 Idempotency Key Bug Fix Rationale`?**
  _Edge tagged AMBIGUOUS (relation: references) - confidence is low._
- **What is the exact relationship between `Knowledge graph (1,162 nodes, 94 communities)` and `Graph Report (GRAPH_REPORT.md)`?**
  _Edge tagged AMBIGUOUS (relation: references) - confidence is low._
- **Why does `ScreeningRecord` connect `ScreeningRecord (AML domain model)` to `AMLScreeningProcessor (AML-hold gate)`?**
  _High betweenness centrality (0.019) - this node is a cross-community bridge._
- **Why does `SettlementRecord` connect `SettlementRecord (settlement domain)` to `ClickHouseAnalyticsService`?**
  _High betweenness centrality (0.012) - this node is a cross-community bridge._
- **Why does `ClearFlowMcpTools` connect `ClearFlowMcpTools (cascade detection)` to `MCP Gateway Tools & Services`?**
  _High betweenness centrality (0.011) - this node is a cross-community bridge._
- **What connects `Read a counter from the Prometheus scrape endpoint.`, `Return total consumer lag for a consumer group, or -1 on error.`, `Read architecture graph from graphify report` to the rest of the system?**
  _177 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `AccessLogService (MCP audit logging)` be split into smaller, more focused modules?**
  _Cohesion score 0.02 - nodes in this community are weakly interconnected._