# Graph Report - .  (2026-09-09)

## Corpus Check
- Large corpus: 415 files · ~301,449 words. Semantic extraction will be expensive (many Claude tokens). Consider running on a subfolder, or use --no-semantic to run AST-only.

## Summary
- 1294 nodes · 1670 edges · 101 communities detected
- Extraction: 80% EXTRACTED · 20% INFERRED · 0% AMBIGUOUS · INFERRED: 330 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## God Nodes (most connected - your core abstractions)
1. `ScreeningRecord` - 43 edges
2. `CascadeFailureDetector` - 29 edges
3. `SettlementRecord` - 27 edges
4. `ValidationRecord` - 25 edges
5. `ClearFlowMcpTools` - 25 edges
6. `ElasticsearchLogFetcher` - 24 edges
7. `PaymentEnrichment` - 23 edges
8. `CodeGraphService` - 22 edges
9. `AuditRecord` - 21 edges
10. `LedgerEntry` - 21 edges

## Surprising Connections (you probably didn't know these)
- `SDN List Screening Obligations` --semantically_similar_to--> `Recommendation 6 — Targeted Financial Sanctions (Terrorism)`  [INFERRED] [semantically similar]
  aml-compliance/src/main/resources/compliance-docs/ofac-policy.txt → aml-compliance/src/main/resources/compliance-docs/fatf-recommendations.txt
- `Correspondent Banking Due Diligence (OFAC)` --semantically_similar_to--> `Correspondent Banking Enhanced Due Diligence (EU)`  [INFERRED] [semantically similar]
  aml-compliance/src/main/resources/compliance-docs/ofac-policy.txt → aml-compliance/src/main/resources/compliance-docs/eu-amld6.txt
- `Shell Bank Prohibition (EU)` --semantically_similar_to--> `Shell Bank Definition (FATF)`  [INFERRED] [semantically similar]
  aml-compliance/src/main/resources/compliance-docs/eu-amld6.txt → aml-compliance/src/main/resources/compliance-docs/fatf-recommendations.txt
- `Iran Sanctions Program (31 CFR Part 560)` --conceptually_related_to--> `Recommendation 7 — Targeted Financial Sanctions (Proliferation)`  [INFERRED]
  aml-compliance/src/main/resources/compliance-docs/ofac-policy.txt → aml-compliance/src/main/resources/compliance-docs/fatf-recommendations.txt
- `North Korea Sanctions Program (31 CFR Part 510)` --conceptually_related_to--> `Recommendation 7 — Targeted Financial Sanctions (Proliferation)`  [EXTRACTED]
  aml-compliance/src/main/resources/compliance-docs/ofac-policy.txt → aml-compliance/src/main/resources/compliance-docs/fatf-recommendations.txt

## Hyperedges (group relationships)
- **OFAC/EU-AMLD6/FATF Regulatory Reference Triad Feeding AML Compliance** — ofacpolicy_doc, eu_amld6_doc, fatf_recommendations_doc, overview_aml_fraud, fuzzy_screening_engine [INFERRED 0.75]

## Communities

### Community 0 - "Messaging & Fault Injection"
Cohesion: 0.03
Nodes (16): ActiveMQPublisher, AMLPatternInjector, CircuitBreakerNames, IdempotencyService, KafkaEventPublisher, MaskedIbanSerializer, PaymentController, PaymentControllerTest (+8 more)

### Community 1 - "AML Screening Core"
Cohesion: 0.03
Nodes (7): AMLScreeningProcessor, ComplianceReviewController, FuzzyMatchTest, FuzzyScreeningEngine, ScreeningRecord, ScreeningRecordRepository, SDNLoader

### Community 2 - "Audit Logging & AML Kafka Consumer"
Cohesion: 0.03
Nodes (14): AccessLogService, AMLKafkaConsumer, DlqPublisher, FraudKafkaConsumerIT, IntegrationTestBase, KafkaTopics, OutboxRelayScheduler, OutboxRelaySchedulerIT (+6 more)

### Community 3 - "Cascade Detection Engine"
Cohesion: 0.04
Nodes (12): CascadeMonitoringService, LLMClient, McpMetricsService, McpRateLimiter, State, MCPTool, McpToolsConfig, PaymentTimelineReconstructor (+4 more)

### Community 4 - "Audit Service API"
Cohesion: 0.04
Nodes (7): AuditController, AuditEventConsumer, AuditRecord, AuditRecordKey, AuditRepository, HashChainIntegrityTest, HashChainService

### Community 5 - "AML Risk Scoring"
Cohesion: 0.05
Nodes (9): CountryRiskMatrix, FeatureEngineeringService, FraudKafkaConsumer, FraudScoringController, FraudScoringService, FraudScoringServiceTest, HeuristicScoringService, LightGBMStubClient (+1 more)

### Community 6 - "Payment Rail Catalog"
Cohesion: 0.06
Nodes (5): PaymentRailRule, RailRules, RailSelectionEngine, RailSelectionProcessor, RailSelectionTest

### Community 7 - "Compliance Tooling"
Cohesion: 0.07
Nodes (4): ComplianceTool, ElasticsearchLogFetcher, FraudScoreTool, PaymentTimelineTool

### Community 8 - "Settlement Analytics & Ledger Tests"
Cohesion: 0.07
Nodes (8): ClickHouseAnalyticsService, DoubleEntryAccountingTest, LedgerRepository, SettlementController, SettlementKafkaConsumer, SettlementProcessor, SettlementRepository, SettlementService

### Community 9 - "AML Regulatory Reference"
Cohesion: 0.09
Nodes (32): Article 3 — ML Offences & 22 Predicate Offences, Article 6 — Criminal Liability of Legal Persons, Article 7 — Sanctions for Legal Persons, Beneficial Ownership Register, Correspondent Banking Enhanced Due Diligence (EU), EU Sixth Anti-Money Laundering Directive (6AMLD), European Banking Authority Supervisory Role, High-Risk Third Countries — Enhanced Measures (+24 more)

### Community 10 - "Validation Enrichment"
Cohesion: 0.07
Nodes (3): EnrichmentProcessor, PaymentEnrichment, PaymentEnrichmentRepository

### Community 11 - "Cascade Z-Score Detector"
Cohesion: 0.14
Nodes (1): CascadeFailureDetector

### Community 12 - "Validation Record Model"
Cohesion: 0.07
Nodes (2): ValidationRecord, ValidationRecordRepository

### Community 13 - "Liquidity Reservation & Release"
Cohesion: 0.08
Nodes (6): LiquidityController, LiquidityReleaseConsumer, LiquidityReservationProcessor, LiquidityReservationService, MQQueues, SagaCompensationRoute

### Community 14 - "Settlement Record Model"
Cohesion: 0.07
Nodes (1): SettlementRecord

### Community 15 - "MCP Tool Surface"
Cohesion: 0.12
Nodes (1): ClearFlowMcpTools

### Community 16 - "Code/Module Graph Builder"
Cohesion: 0.14
Nodes (1): CodeGraphService

### Community 17 - "Ledger Entry Model"
Cohesion: 0.1
Nodes (1): LedgerEntry

### Community 18 - "Traffic Simulator Config"
Cohesion: 0.11
Nodes (1): SimulatorConfig

### Community 19 - "Frontend Dashboard Client"
Cohesion: 0.23
Nodes (17): cacheRead(), cacheWrite(), fetchAlerts(), fetchCached(), fetchChat(), fetchExplain(), fetchFraudMetrics(), fetchOverview() (+9 more)

### Community 20 - "Demo Scenario Seeder"
Cohesion: 0.25
Nodes (1): DemoScenarioSeeder

### Community 21 - "MCP Chat/Explain API"
Cohesion: 0.21
Nodes (1): MCPController

### Community 22 - "RCA Classifier Tests"
Cohesion: 0.29
Nodes (1): RootCauseClassifierTest

### Community 23 - "Predictive Cascade Simulator"
Cohesion: 0.17
Nodes (2): PredictiveCascadeSimulator, PredictiveController

### Community 24 - "RCA Classifier Core"
Cohesion: 0.35
Nodes (1): RootCauseClassifier

### Community 25 - "Community 25"
Cohesion: 0.17
Nodes (1): CascadeDetectionController

### Community 26 - "Community 26"
Cohesion: 0.29
Nodes (1): FraudPatternInjector

### Community 27 - "Community 27"
Cohesion: 0.27
Nodes (1): PaymentTimelineReconstructorTest

### Community 28 - "Community 28"
Cohesion: 0.32
Nodes (1): ForecastSettlementService

### Community 29 - "Community 29"
Cohesion: 0.2
Nodes (1): PromptTemplates

### Community 30 - "Community 30"
Cohesion: 0.33
Nodes (1): TransactionPatternLibrary

### Community 31 - "Community 31"
Cohesion: 0.33
Nodes (1): CascadeAlertingService

### Community 32 - "Community 32"
Cohesion: 0.29
Nodes (5): AlertRow(), Dashboard(), fmt(), fmtTs(), seedFromCache()

### Community 33 - "Community 33"
Cohesion: 0.22
Nodes (2): buildPayload(), uuid()

### Community 34 - "Community 34"
Cohesion: 0.25
Nodes (1): PaymentArchTest

### Community 35 - "Community 35"
Cohesion: 0.46
Nodes (1): DemoDataLoader

### Community 36 - "Community 36"
Cohesion: 0.36
Nodes (1): AgentRegistry

### Community 37 - "Community 37"
Cohesion: 0.57
Nodes (1): SettlementKafkaConsumerIT

### Community 38 - "Community 38"
Cohesion: 0.29
Nodes (2): GlobalExceptionHandler, ProblemDetailBuilder

### Community 39 - "Community 39"
Cohesion: 0.48
Nodes (1): UETRTrackerController

### Community 40 - "Community 40"
Cohesion: 0.43
Nodes (1): IbanGeneratorUtil

### Community 41 - "Community 41"
Cohesion: 0.43
Nodes (1): AdminController

### Community 42 - "Community 42"
Cohesion: 0.43
Nodes (1): SettlementKafkaConfig

### Community 43 - "Community 43"
Cohesion: 0.4
Nodes (1): FraudKafkaConfig

### Community 44 - "Community 44"
Cohesion: 0.47
Nodes (1): ValidationKafkaConfig

### Community 45 - "Community 45"
Cohesion: 0.47
Nodes (1): FallbackLLMClient

### Community 46 - "Community 46"
Cohesion: 0.47
Nodes (1): RoutingKafkaConfig

### Community 47 - "Community 47"
Cohesion: 0.4
Nodes (2): buildPayload(), uuid()

### Community 48 - "Community 48"
Cohesion: 0.33
Nodes (0): 

### Community 49 - "Community 49"
Cohesion: 0.47
Nodes (1): AMLKafkaConfig

### Community 50 - "Community 50"
Cohesion: 0.5
Nodes (1): SecurityConfig

### Community 51 - "Community 51"
Cohesion: 0.5
Nodes (1): GatewayKafkaProducerConfig

### Community 52 - "Community 52"
Cohesion: 0.4
Nodes (1): NvidiaLLMClient

### Community 53 - "Community 53"
Cohesion: 0.4
Nodes (1): OpenRouterLLMClient

### Community 54 - "Community 54"
Cohesion: 0.4
Nodes (1): OllamaLLMClient

### Community 55 - "Community 55"
Cohesion: 0.5
Nodes (1): MCPSecurityConfig

### Community 56 - "Community 56"
Cohesion: 0.5
Nodes (1): MetricsTool

### Community 57 - "Community 57"
Cohesion: 0.5
Nodes (2): extractService(), LogEntry()

### Community 58 - "Community 58"
Cohesion: 0.4
Nodes (0): 

### Community 59 - "Community 59"
Cohesion: 0.67
Nodes (1): GatewayKafkaConsumerConfig

### Community 60 - "Community 60"
Cohesion: 0.5
Nodes (1): IBANValidationProcessor

### Community 61 - "Community 61"
Cohesion: 0.5
Nodes (1): CurrencyValidationProcessor

### Community 62 - "Community 62"
Cohesion: 0.5
Nodes (1): BICValidationProcessor

### Community 63 - "Community 63"
Cohesion: 0.5
Nodes (1): EmbargoPreCheckProcessor

### Community 64 - "Community 64"
Cohesion: 0.5
Nodes (1): EmbargoDataLoader

### Community 65 - "Community 65"
Cohesion: 0.5
Nodes (1): LLMConfig

### Community 66 - "Community 66"
Cohesion: 0.5
Nodes (1): ErrorBoundary

### Community 67 - "Community 67"
Cohesion: 0.67
Nodes (1): CorrelationIdFilter

### Community 68 - "Community 68"
Cohesion: 0.67
Nodes (1): PiiMaskingConverter

### Community 69 - "Community 69"
Cohesion: 0.67
Nodes (1): MetricsConstants

### Community 70 - "Community 70"
Cohesion: 0.67
Nodes (1): DuplicatePaymentException

### Community 71 - "Community 71"
Cohesion: 0.67
Nodes (1): PaymentException

### Community 72 - "Community 72"
Cohesion: 0.67
Nodes (1): GatewayApplication

### Community 73 - "Community 73"
Cohesion: 0.67
Nodes (1): IbanValidator

### Community 74 - "Community 74"
Cohesion: 0.67
Nodes (1): DevSecurityConfig

### Community 75 - "Community 75"
Cohesion: 0.67
Nodes (1): FraudScoringApplication

### Community 76 - "Community 76"
Cohesion: 0.67
Nodes (1): ValidationEnrichmentApplication

### Community 77 - "Community 77"
Cohesion: 0.67
Nodes (1): ValidationEnrichmentCamelRoute

### Community 78 - "Community 78"
Cohesion: 0.67
Nodes (1): CamelKafkaConfig

### Community 79 - "Community 79"
Cohesion: 0.67
Nodes (1): McpReadonlyGatewayApplication

### Community 80 - "Community 80"
Cohesion: 0.67
Nodes (1): JwtScopeConverter

### Community 81 - "Community 81"
Cohesion: 0.67
Nodes (1): AuditApplication

### Community 82 - "Community 82"
Cohesion: 0.67
Nodes (1): CassandraConfig

### Community 83 - "Community 83"
Cohesion: 0.67
Nodes (1): AuditKafkaErrorHandler

### Community 84 - "Community 84"
Cohesion: 0.67
Nodes (1): AuditKafkaConfig

### Community 85 - "Community 85"
Cohesion: 0.67
Nodes (1): RoutingExecutionApplication

### Community 86 - "Community 86"
Cohesion: 0.67
Nodes (1): RoutingCamelRoute

### Community 87 - "Community 87"
Cohesion: 0.67
Nodes (1): InsufficientLiquidityException

### Community 88 - "Community 88"
Cohesion: 0.67
Nodes (0): 

### Community 89 - "Community 89"
Cohesion: 0.67
Nodes (1): AmlComplianceApplication

### Community 90 - "Community 90"
Cohesion: 0.67
Nodes (1): AMLCamelRoute

### Community 91 - "Community 91"
Cohesion: 0.67
Nodes (1): SettlementApplication

### Community 92 - "Community 92"
Cohesion: 0.67
Nodes (1): SettlementCamelRoute

### Community 93 - "Community 93"
Cohesion: 0.67
Nodes (1): SettlementFinalityViolationException

### Community 94 - "Community 94"
Cohesion: 1.0
Nodes (0): 

### Community 95 - "Community 95"
Cohesion: 1.0
Nodes (0): 

### Community 96 - "Community 96"
Cohesion: 1.0
Nodes (0): 

### Community 97 - "Community 97"
Cohesion: 1.0
Nodes (0): 

### Community 98 - "Community 98"
Cohesion: 1.0
Nodes (0): 

### Community 99 - "Community 99"
Cohesion: 1.0
Nodes (0): 

### Community 100 - "Community 100"
Cohesion: 1.0
Nodes (0): 

## Knowledge Gaps
- **9 isolated node(s):** `TestApp`, `PaymentEnrichmentRepository`, `ValidationRecordRepository`, `General and Specific Licenses`, `Blocking vs Rejecting Transactions` (+4 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 94`** (2 nodes): `GraphifyViewer.jsx`, `GraphifyViewer()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 95`** (2 nodes): `NavBar.jsx`, `NavBar()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 96`** (2 nodes): `DashboardTabs.jsx`, `DashboardTabs()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 97`** (1 nodes): `Iban.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 98`** (1 nodes): `PaymentChannel.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 99`** (1 nodes): `UETRTrackingResponse.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 100`** (1 nodes): `vite.config.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `CascadeFailureDetector` connect `Cascade Z-Score Detector` to `Cascade Detection Engine`?**
  _High betweenness centrality (0.029) - this node is a cross-community bridge._
- **Why does `SettlementRecord` connect `Settlement Record Model` to `Settlement Analytics & Ledger Tests`?**
  _High betweenness centrality (0.027) - this node is a cross-community bridge._
- **What connects `TestApp`, `PaymentEnrichmentRepository`, `ValidationRecordRepository` to the rest of the system?**
  _9 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Messaging & Fault Injection` be split into smaller, more focused modules?**
  _Cohesion score 0.03 - nodes in this community are weakly interconnected._
- **Should `AML Screening Core` be split into smaller, more focused modules?**
  _Cohesion score 0.03 - nodes in this community are weakly interconnected._
- **Should `Audit Logging & AML Kafka Consumer` be split into smaller, more focused modules?**
  _Cohesion score 0.03 - nodes in this community are weakly interconnected._
- **Should `Cascade Detection Engine` be split into smaller, more focused modules?**
  _Cohesion score 0.04 - nodes in this community are weakly interconnected._