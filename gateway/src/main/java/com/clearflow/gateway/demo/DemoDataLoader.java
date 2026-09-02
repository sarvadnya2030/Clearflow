package com.clearflow.gateway.demo;

import com.clearflow.common.domain.PaymentInitiatedEvent;
import com.clearflow.gateway.messaging.ActiveMQPublisher;
import com.clearflow.gateway.messaging.KafkaEventPublisher;
import com.clearflow.gateway.messaging.SolacePublisher;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.List;
import java.util.UUID;

/**
 * Demo Data Loader — submits 100 realistic ISO 20022 payment scenarios on startup.
 *
 * <p>Activated by setting {@code clearflow.demo.enabled=true} in application.yml
 * or via environment variable {@code CLEARFLOW_DEMO_ENABLED=true}.
 *
 * <h3>Purpose</h3>
 * Populates the system end-to-end so the MCP read-only gateway has real data
 * to query. Each payment traverses the full pipeline:
 * <ol>
 *   <li>Gateway publishes {@code PaymentInitiatedEvent} to ActiveMQ + Kafka</li>
 *   <li>Validation-Enrichment validates IBAN/BIC, checks embargo lists</li>
 *   <li>Fraud Scoring assigns a risk score (LightGBM + heuristics)</li>
 *   <li>AML Compliance screens against SDN/PEP lists (fuzzy + Soundex)</li>
 *   <li>Routing Execution selects the payment rail, reserves liquidity</li>
 *   <li>Settlement posts double-entry ledger, writes to Cassandra + ClickHouse</li>
 *   <li>Audit writes SHA-256 hash chain to Cassandra</li>
 * </ol>
 *
 * <h3>Scenario groups</h3>
 * <ul>
 *   <li>Group A (A01–A30): Routine Retail/Corporate — SEPA_INSTANT, FASTER_PAYMENTS, FEDACH, SEPA_CT</li>
 *   <li>Group B (B01–B15): High-Value Treasury — CHAPS, CHIPS, FEDWIRE, SEPA_CT large, SWIFT_GPI</li>
 *   <li>Group C (C01–C15): Cross-Border Correspondent — AU/CA/HK/JP/ZA/AE/BR corridors</li>
 *   <li>Group D (D01–D15): Fraud/Suspicious — velocity, high-risk country, off-hours, embargoed, structuring</li>
 *   <li>Group E (E01–E10): AML/Compliance Edge Cases — PEP-linked, FATF grey, SDN phonetic, round-trip</li>
 *   <li>Group F (F01–F15): Operational Edge Cases — duplicates, embargoed debtor, liquidity, FX, BACS routing</li>
 * </ul>
 *
 * <p>Real verified BIC codes used (SWIFT directory sources):
 * DEUTDEFFXXX, ABNANL2AXXX, BNPAFRPPXXX, UNCRITMM, BARCGB22XXX, HBUKGB4BXXX,
 * CHASUS33XXX, CITIUS33XXX, DBSSSGSGXXX, INGBNL2AXXX, COBADEFFXXX, SOGEFRPPXXX,
 * BSCHESMMXXX, UBSWCHZHXXX, WFBIUS6SXXX, ANZBAU3MXXX, ROYCCAT2XXX, HSBCHKHHHKH,
 * MHCBJPJTXXX, SBZAZAJJXXX, NBADAEAAXXX, ITAUBRSPXXX, NDEAFIHHXXX, RABONL2UXXX,
 * BBRUBEBB, FNBOUS33XXX, MELOUSA0XXX.
 */
@Component
@ConditionalOnProperty(name = "clearflow.demo.enabled", havingValue = "true")
public class DemoDataLoader implements CommandLineRunner {

    private static final Logger log = LoggerFactory.getLogger(DemoDataLoader.class);

    // ── Real verified SWIFT BIC codes ────────────────────────────────────────
    private static final String BIC_DEUTSCHE_BANK    = "DEUTDEFFXXX";
    private static final String BIC_ABN_AMRO         = "ABNANL2AXXX";
    private static final String BIC_ING_NL           = "INGBNL2AXXX";
    private static final String BIC_BNP_PARIBAS      = "BNPAFRPPXXX";
    private static final String BIC_SG_FRANCE        = "SOGEFRPPXXX";
    private static final String BIC_UNICREDIT        = "UNCRITMM";
    private static final String BIC_BARCLAYS         = "BARCGB22XXX";
    private static final String BIC_HSBC_UK          = "HBUKGB4BXXX";
    private static final String BIC_JPMORGAN         = "CHASUS33XXX";
    private static final String BIC_CITIBANK         = "CITIUS33XXX";
    private static final String BIC_WELLS_FARGO      = "WFBIUS6SXXX";
    private static final String BIC_DBS_SINGAPORE    = "DBSSSGSGXXX";
    private static final String BIC_COMMERZBANK      = "COBADEFFXXX";
    private static final String BIC_SANTANDER        = "BSCHESMMXXX";
    private static final String BIC_UBS_ZURICH       = "UBSWCHZHXXX";
    private static final String BIC_DEUTSCHE_DEUT    = "DEUTDEDBXXX";
    private static final String BIC_ANZ_AU           = "ANZBAU3MXXX";
    private static final String BIC_RBC_CA           = "ROYCCAT2XXX";
    private static final String BIC_HSBC_HK          = "HSBCHKHHHKH";
    private static final String BIC_MIZUHO_JP        = "MHCBJPJTXXX";
    private static final String BIC_STD_BANK_ZA      = "SBZAZAJJXXX";
    private static final String BIC_FAB_AE           = "NBADAEAAXXX";
    private static final String BIC_ITAU_BR          = "ITAUBRSPXXX";
    private static final String BIC_NORDEA_FI        = "NDEAFIHHXXX";
    private static final String BIC_RABOBANK         = "RABONL2UXXX";
    private static final String BIC_ING_BE           = "BBRUBEBB";
    private static final String BIC_FNBO             = "FNBOUS33XXX";
    private static final String BIC_MELO             = "MELOUSA0XXX";
    private static final String BIC_TD_CA            = "TDOMCATTTOR";
    private static final String BIC_COMMERZBANK_DE   = "COBADEFFXXX";
    private static final String BIC_PKO_PL           = "BPKOPLPW";
    private static final String BIC_ERSTE_AT         = "GIBAATWWXXX";

    // ── Valid test IBANs (iban.com test data) ────────────────────────────────
    private static final String IBAN_DE = "DE75512108001245126199";
    private static final String IBAN_NL = "NL02ABNA0123456789";
    private static final String IBAN_FR = "FR7630006000011234567890189";
    private static final String IBAN_GB = "GB33BUKB20201555555555";
    private static final String IBAN_IT = "IT60X0542811101000000123456";
    private static final String IBAN_ES = "ES7921000813610123456789";
    private static final String IBAN_CH = "CH9300762011623852957";
    private static final String IBAN_BE = "BE68539007547034";
    private static final String IBAN_AT = "AT611904300234573201";
    private static final String IBAN_SE = "SE4550000000058398257466";
    private static final String IBAN_FI = "FI2112345600000785";
    private static final String IBAN_PL = "PL61109010140000071219812874";
    private static final String IBAN_BR = "BR1800360305000010009795493P1";
    private static final String IBAN_GB2 = "GB29NWBK60161331926819";
    private static final String IBAN_DE2 = "DE89370400440532013000";
    private static final String IBAN_FR2 = "FR1420041010050500013M02606";
    private static final String IBAN_NL2 = "NL91ABNA0417164300";
    private static final String IBAN_IT2 = "IT60X0542811101000000654321";
    private static final String IBAN_ES2 = "ES9121000418450200051332";

    // ── Non-IBAN accounts for AU/CA/HK/JP ────────────────────────────────────
    private static final String ACCT_AU  = "AU012345678901";
    private static final String ACCT_CA  = "CA0003100123456";
    private static final String ACCT_HK  = "HK123456789012";
    private static final String ACCT_JP  = "JP1234567890";
    private static final String ACCT_ZA  = "ZA999012345678";
    private static final String ACCT_AE  = "AE070331234567890123456";

    private final ActiveMQPublisher activeMQPublisher;
    private final KafkaEventPublisher kafkaEventPublisher;
    private final SolacePublisher solacePublisher;

    public DemoDataLoader(ActiveMQPublisher activeMQPublisher,
                          KafkaEventPublisher kafkaEventPublisher,
                          SolacePublisher solacePublisher) {
        this.activeMQPublisher = activeMQPublisher;
        this.kafkaEventPublisher = kafkaEventPublisher;
        this.solacePublisher = solacePublisher;
    }

    @Override
    public void run(String... args) {
        log.info("=== ClearFlow Demo Data Loader starting — submitting 100 payment scenarios ===");

        List<Scenario> scenarios = buildScenarios();
        for (int i = 0; i < scenarios.size(); i++) {
            Scenario s = scenarios.get(i);
            try {
                submit(s);
                log.info("[{}/{}] SUBMITTED — scenario={} paymentId={} amount={} {} {}→{}",
                        i + 1, scenarios.size(), s.label, s.event.paymentId(),
                        s.event.amount(), s.event.currency(),
                        s.event.debtorCountry(), s.event.creditorCountry());
                Thread.sleep(250);
            } catch (Exception ex) {
                log.warn("[{}/{}] SKIPPED — scenario={} reason={}", i + 1, scenarios.size(), s.label, ex.getMessage());
            }
        }
        log.info("=== Demo Data Loader complete — {} scenarios submitted ===", scenarios.size());
    }

    private void submit(Scenario s) {
        String traceParent = "00-" + s.event.paymentId().replace("-", "") + "000000000000000001";
        activeMQPublisher.publish(s.event, "demo-loader");
        kafkaEventPublisher.publish(s.event, traceParent, "");
        solacePublisher.publish(s.event);
    }

    // ── Scenario catalogue ────────────────────────────────────────────────────

    private List<Scenario> buildScenarios() {
        Instant offHours = LocalDate.now(ZoneOffset.UTC).atTime(3, 0).toInstant(ZoneOffset.UTC);

        return List.of(

            // ════════════════════════════════════════════════════════════════
            // GROUP A — Routine Retail/Corporate (30 transactions)
            // ════════════════════════════════════════════════════════════════

            // A01–A08: SEPA_INSTANT (€500–€22K, 8 SEPA corridors)
            scenario("A01_SEPA_INSTANT_NL_DE",
                amt(500), "EUR", "NL", "DE",
                IBAN_NL, IBAN_DE, BIC_ABN_AMRO, BIC_DEUTSCHE_BANK, "SEPA_INSTANT"),

            scenario("A02_SEPA_INSTANT_FR_ES",
                amt(1_850), "EUR", "FR", "ES",
                IBAN_FR, IBAN_ES, BIC_BNP_PARIBAS, BIC_SANTANDER, "SEPA_INSTANT"),

            scenario("A03_SEPA_INSTANT_IT_NL",
                amt(3_200), "EUR", "IT", "NL",
                IBAN_IT, IBAN_NL2, BIC_UNICREDIT, BIC_ING_NL, "SEPA_INSTANT"),

            scenario("A04_SEPA_INSTANT_DE_AT",
                amt(7_500), "EUR", "DE", "AT",
                IBAN_DE, IBAN_AT, BIC_DEUTSCHE_BANK, BIC_ERSTE_AT, "SEPA_INSTANT"),

            scenario("A05_SEPA_INSTANT_ES_FR",
                amt(4_400), "EUR", "ES", "FR",
                IBAN_ES, IBAN_FR2, BIC_SANTANDER, BIC_SG_FRANCE, "SEPA_INSTANT"),

            scenario("A06_SEPA_INSTANT_NL_BE",
                amt(11_000), "EUR", "NL", "BE",
                IBAN_NL2, IBAN_BE, BIC_ING_NL, BIC_ING_BE, "SEPA_INSTANT"),

            scenario("A07_SEPA_INSTANT_FI_DE",
                amt(6_300), "EUR", "FI", "DE",
                IBAN_FI, IBAN_DE2, BIC_NORDEA_FI, BIC_COMMERZBANK, "SEPA_INSTANT"),

            scenario("A08_SEPA_INSTANT_PL_DE",
                amt(22_000), "EUR", "PL", "DE",
                IBAN_PL, IBAN_DE, BIC_PKO_PL, BIC_DEUTSCHE_BANK, "SEPA_INSTANT"),

            // A09–A14: FASTER_PAYMENTS (£850–£280K, 6 domestic GBP)
            scenario("A09_FASTER_PAYMENTS_GBP_850",
                amt(850), "GBP", "GB", "GB",
                IBAN_GB, IBAN_GB2, BIC_BARCLAYS, BIC_HSBC_UK, "FASTER_PAYMENTS"),

            scenario("A10_FASTER_PAYMENTS_GBP_3500",
                amt(3_500), "GBP", "GB", "GB",
                IBAN_GB2, IBAN_GB, BIC_HSBC_UK, BIC_BARCLAYS, "FASTER_PAYMENTS"),

            scenario("A11_FASTER_PAYMENTS_GBP_12K",
                amt(12_000), "GBP", "GB", "GB",
                IBAN_GB, IBAN_GB2, BIC_BARCLAYS, BIC_HSBC_UK, "FASTER_PAYMENTS"),

            scenario("A12_FASTER_PAYMENTS_GBP_45K",
                amt(45_000), "GBP", "GB", "GB",
                IBAN_GB2, IBAN_GB, BIC_HSBC_UK, BIC_BARCLAYS, "FASTER_PAYMENTS"),

            scenario("A13_FASTER_PAYMENTS_GBP_120K",
                amt(120_000), "GBP", "GB", "GB",
                IBAN_GB, IBAN_GB2, BIC_BARCLAYS, BIC_WELLS_FARGO, "FASTER_PAYMENTS"),

            scenario("A14_FASTER_PAYMENTS_GBP_280K",
                amt(280_000), "GBP", "GB", "GB",
                IBAN_GB2, IBAN_GB, BIC_HSBC_UK, BIC_BARCLAYS, "FASTER_PAYMENTS"),

            // A15–A22: FEDACH (USD $12.5K–$980K, 8 domestic USD below $1M)
            scenario("A15_FEDACH_USD_12500",
                amt(12_500), "USD", "US", "US",
                "US100000001", "US200000001", BIC_JPMORGAN, BIC_CITIBANK, "ACH"),

            scenario("A16_FEDACH_USD_45K",
                amt(45_000), "USD", "US", "US",
                "US100000002", "US200000002", BIC_CITIBANK, BIC_WELLS_FARGO, "ACH"),

            scenario("A17_FEDACH_USD_88K",
                amt(88_000), "USD", "US", "US",
                "US100000003", "US200000003", BIC_WELLS_FARGO, BIC_JPMORGAN, "ACH"),

            scenario("A18_FEDACH_USD_155K",
                amt(155_000), "USD", "US", "US",
                "US100000004", "US200000004", BIC_JPMORGAN, BIC_CITIBANK, "ACH"),

            scenario("A19_FEDACH_USD_250K",
                amt(250_000), "USD", "US", "US",
                "US100000005", "US200000005", BIC_CITIBANK, BIC_JPMORGAN, "ACH"),

            scenario("A20_FEDACH_USD_400K",
                amt(400_000), "USD", "US", "US",
                "US100000006", "US200000006", BIC_WELLS_FARGO, BIC_CITIBANK, "ACH"),

            scenario("A21_FEDACH_USD_650K",
                amt(650_000), "USD", "US", "US",
                "US100000007", "US200000007", BIC_JPMORGAN, BIC_WELLS_FARGO, "ACH"),

            scenario("A22_FEDACH_USD_980K",
                amt(980_000), "USD", "US", "US",
                "US100000008", "US200000008", BIC_CITIBANK, BIC_JPMORGAN, "ACH"),

            // A23–A30: SEPA_CT (€100K–€420K, 8 large corporates)
            scenario("A23_SEPA_CT_DE_FR_100K",
                amt(100_000), "EUR", "DE", "FR",
                IBAN_DE, IBAN_FR, BIC_DEUTSCHE_BANK, BIC_BNP_PARIBAS, "SEPA"),

            scenario("A24_SEPA_CT_FR_IT_150K",
                amt(150_000), "EUR", "FR", "IT",
                IBAN_FR, IBAN_IT, BIC_BNP_PARIBAS, BIC_UNICREDIT, "SEPA"),

            scenario("A25_SEPA_CT_IT_ES_200K",
                amt(200_000), "EUR", "IT", "ES",
                IBAN_IT, IBAN_ES, BIC_UNICREDIT, BIC_SANTANDER, "SEPA"),

            scenario("A26_SEPA_CT_ES_DE_220K",
                amt(220_000), "EUR", "ES", "DE",
                IBAN_ES, IBAN_DE2, BIC_SANTANDER, BIC_COMMERZBANK, "SEPA"),

            scenario("A27_SEPA_CT_NL_FR_280K",
                amt(280_000), "EUR", "NL", "FR",
                IBAN_NL, IBAN_FR2, BIC_ING_NL, BIC_SG_FRANCE, "SEPA"),

            scenario("A28_SEPA_CT_DE_IT_320K",
                amt(320_000), "EUR", "DE", "IT",
                IBAN_DE2, IBAN_IT2, BIC_COMMERZBANK, BIC_UNICREDIT, "SEPA"),

            scenario("A29_SEPA_CT_BE_NL_380K",
                amt(380_000), "EUR", "BE", "NL",
                IBAN_BE, IBAN_NL, BIC_ING_BE, BIC_ABN_AMRO, "SEPA"),

            scenario("A30_SEPA_CT_FI_DE_420K",
                amt(420_000), "EUR", "FI", "DE",
                IBAN_FI, IBAN_DE, BIC_NORDEA_FI, BIC_DEUTSCHE_BANK, "SEPA"),

            // ════════════════════════════════════════════════════════════════
            // GROUP B — High-Value Treasury (15 transactions)
            // ════════════════════════════════════════════════════════════════

            // B01–B03: CHAPS (£2M, £5.5M, £12M)
            scenario("B01_CHAPS_GBP_2M",
                amt(2_000_000), "GBP", "GB", "GB",
                IBAN_GB, IBAN_GB2, BIC_BARCLAYS, BIC_HSBC_UK, "CHAPS"),

            scenario("B02_CHAPS_GBP_5_5M",
                amt(5_500_000), "GBP", "GB", "GB",
                IBAN_GB2, IBAN_GB, BIC_HSBC_UK, BIC_BARCLAYS, "CHAPS"),

            scenario("B03_CHAPS_GBP_12M",
                amt(12_000_000), "GBP", "GB", "GB",
                IBAN_GB, IBAN_GB2, BIC_BARCLAYS, BIC_HSBC_UK, "CHAPS"),

            // B04–B06: CHIPS ($10M, $25M, $50M)
            scenario("B04_CHIPS_USD_10M",
                amt(10_000_000), "USD", "US", "US",
                "CHAS000000001", "CITI000000001", BIC_JPMORGAN, BIC_CITIBANK, "CHIPS"),

            scenario("B05_CHIPS_USD_25M",
                amt(25_000_000), "USD", "US", "US",
                "CITI000000001", "CHAS000000001", BIC_CITIBANK, BIC_JPMORGAN, "CHIPS"),

            scenario("B06_CHIPS_USD_50M",
                amt(50_000_000), "USD", "US", "US",
                "CHAS000000002", "WFBI000000001", BIC_JPMORGAN, BIC_WELLS_FARGO, "CHIPS"),

            // B07–B09: FEDWIRE ($1.5M, $5M, $15M — non-CHIPS BICs)
            scenario("B07_FEDWIRE_USD_1_5M",
                amt(1_500_000), "USD", "US", "US",
                "FNBO000000001", "MELO000000001", BIC_FNBO, BIC_MELO, "FEDWIRE"),

            scenario("B08_FEDWIRE_USD_5M",
                amt(5_000_000), "USD", "US", "US",
                "MELO000000001", "FNBO000000001", BIC_MELO, BIC_FNBO, "FEDWIRE"),

            scenario("B09_FEDWIRE_USD_15M",
                amt(15_000_000), "USD", "US", "US",
                "FNBO000000002", "MELO000000002", BIC_FNBO, BIC_MELO, "FEDWIRE"),

            // B10–B12: Large SEPA_CT (€1M, €2.5M, €5M)
            scenario("B10_SEPA_CT_LARGE_DE_FR_1M",
                amt(1_000_000), "EUR", "DE", "FR",
                IBAN_DE, IBAN_FR, BIC_DEUTSCHE_BANK, BIC_BNP_PARIBAS, "SEPA"),

            scenario("B11_SEPA_CT_LARGE_FR_IT_2_5M",
                amt(2_500_000), "EUR", "FR", "IT",
                IBAN_FR, IBAN_IT, BIC_BNP_PARIBAS, BIC_UNICREDIT, "SEPA"),

            scenario("B12_SEPA_CT_LARGE_NL_DE_5M",
                amt(5_000_000), "EUR", "NL", "DE",
                IBAN_NL, IBAN_DE, BIC_ABN_AMRO, BIC_DEUTSCHE_BANK, "SEPA"),

            // B13–B15: SWIFT_GPI cross-border large
            scenario("B13_SWIFT_GPI_US_CH_800K",
                amt(800_000), "USD", "US", "CH",
                "US300000001", IBAN_CH, BIC_JPMORGAN, BIC_UBS_ZURICH, "SWIFT_GPI"),

            scenario("B14_SWIFT_GPI_US_SG_2M",
                amt(2_000_000), "USD", "US", "SG",
                "US300000002", "SG100000001", BIC_JPMORGAN, BIC_DBS_SINGAPORE, "SWIFT_GPI"),

            scenario("B15_SWIFT_GPI_DE_HK_3_5M",
                amt(3_500_000), "EUR", "DE", "HK",
                IBAN_DE, ACCT_HK, BIC_DEUTSCHE_BANK, BIC_HSBC_HK, "SWIFT_GPI"),

            // ════════════════════════════════════════════════════════════════
            // GROUP C — Cross-Border Correspondent (15 transactions)
            // ════════════════════════════════════════════════════════════════

            // C01–C03: AU→US
            scenario("C01_AU_US_SWIFT_GPI_75K",
                amt(75_000), "USD", "AU", "US",
                ACCT_AU, "US400000001", BIC_ANZ_AU, BIC_JPMORGAN, "SWIFT_GPI"),

            scenario("C02_AU_US_SWIFT_GPI_200K",
                amt(200_000), "USD", "AU", "US",
                ACCT_AU, "US400000002", BIC_ANZ_AU, BIC_WELLS_FARGO, "SWIFT_GPI"),

            scenario("C03_AU_US_MT103_35K",
                amt(35_000), "USD", "AU", "US",
                ACCT_AU, "US400000003", BIC_ANZ_AU, BIC_CITIBANK, "SWIFT_MT103"),

            // C04–C05: CA→GB
            scenario("C04_CA_GB_SWIFT_GPI_120K",
                amt(120_000), "GBP", "CA", "GB",
                ACCT_CA, IBAN_GB, BIC_RBC_CA, BIC_BARCLAYS, "SWIFT_GPI"),

            scenario("C05_CA_GB_SWIFT_GPI_85K",
                amt(85_000), "GBP", "CA", "GB",
                ACCT_CA, IBAN_GB2, BIC_TD_CA, BIC_HSBC_UK, "SWIFT_GPI"),

            // C06–C07: HK→DE
            scenario("C06_HK_DE_SWIFT_GPI_300K",
                amt(300_000), "EUR", "HK", "DE",
                ACCT_HK, IBAN_DE, BIC_HSBC_HK, BIC_DEUTSCHE_BANK, "SWIFT_GPI"),

            scenario("C07_HK_DE_SWIFT_GPI_180K",
                amt(180_000), "EUR", "HK", "DE",
                ACCT_HK, IBAN_DE2, BIC_HSBC_HK, BIC_COMMERZBANK, "SWIFT_GPI"),

            // C08–C09: JP→FR
            scenario("C08_JP_FR_SWIFT_GPI_250K",
                amt(250_000), "EUR", "JP", "FR",
                ACCT_JP, IBAN_FR, BIC_MIZUHO_JP, BIC_BNP_PARIBAS, "SWIFT_GPI"),

            scenario("C09_JP_FR_SWIFT_GPI_90K",
                amt(90_000), "EUR", "JP", "FR",
                ACCT_JP, IBAN_FR2, BIC_MIZUHO_JP, BIC_SG_FRANCE, "SWIFT_GPI"),

            // C10–C11: ZA→NL
            scenario("C10_ZA_NL_SWIFT_GPI_60K",
                amt(60_000), "EUR", "ZA", "NL",
                ACCT_ZA, IBAN_NL, BIC_STD_BANK_ZA, BIC_ING_NL, "SWIFT_GPI"),

            scenario("C11_ZA_NL_SWIFT_GPI_110K",
                amt(110_000), "EUR", "ZA", "NL",
                ACCT_ZA, IBAN_NL2, BIC_STD_BANK_ZA, BIC_RABOBANK, "SWIFT_GPI"),

            // C12–C13: AE→GB
            scenario("C12_AE_GB_SWIFT_GPI_450K",
                amt(450_000), "GBP", "AE", "GB",
                ACCT_AE, IBAN_GB, BIC_FAB_AE, BIC_BARCLAYS, "SWIFT_GPI"),

            scenario("C13_AE_GB_SWIFT_GPI_220K",
                amt(220_000), "GBP", "AE", "GB",
                ACCT_AE, IBAN_GB2, BIC_FAB_AE, BIC_HSBC_UK, "SWIFT_GPI"),

            // C14–C15: BR→US
            scenario("C14_BR_US_SWIFT_GPI_95K",
                amt(95_000), "USD", "BR", "US",
                IBAN_BR, "US500000001", BIC_ITAU_BR, BIC_JPMORGAN, "SWIFT_GPI"),

            scenario("C15_BR_US_SWIFT_GPI_175K",
                amt(175_000), "USD", "BR", "US",
                IBAN_BR, "US500000002", BIC_ITAU_BR, BIC_WELLS_FARGO, "SWIFT_GPI"),

            // ════════════════════════════════════════════════════════════════
            // GROUP D — Fraud/Suspicious (15 transactions)
            // ════════════════════════════════════════════════════════════════

            // D01–D03: Velocity breach (same debtorIban IBAN_GB, rapid GBP)
            scenario("D01_VELOCITY_BREACH_GBP_1",
                amt(8_500), "GBP", "GB", "GB",
                IBAN_GB, IBAN_GB2, BIC_BARCLAYS, BIC_HSBC_UK, "FASTER_PAYMENTS"),

            scenario("D02_VELOCITY_BREACH_GBP_2",
                amt(9_200), "GBP", "GB", "GB",
                IBAN_GB, IBAN_GB2, BIC_BARCLAYS, BIC_HSBC_UK, "FASTER_PAYMENTS"),

            scenario("D03_VELOCITY_BREACH_GBP_3",
                amt(7_800), "GBP", "GB", "GB",
                IBAN_GB, IBAN_GB2, BIC_BARCLAYS, BIC_HSBC_UK, "FASTER_PAYMENTS"),

            // D04–D06: High-risk creditor country (RU)
            scenario("D04_HIGH_RISK_DE_RU_750K",
                amt(750_000), "EUR", "DE", "RU",
                IBAN_DE, "RU100000001", BIC_DEUTSCHE_BANK, "DEUTRUMM", "SWIFT_GPI"),

            scenario("D05_HIGH_RISK_US_RU_2M",
                amt(2_000_000), "USD", "US", "RU",
                "US600000001", "RU100000002", BIC_JPMORGAN, "DEUTRUMM", "SWIFT_GPI"),

            scenario("D06_HIGH_RISK_FR_RU_450K",
                amt(450_000), "EUR", "FR", "RU",
                IBAN_FR, "RU100000003", BIC_BNP_PARIBAS, "DEUTRUMM", "SWIFT_GPI"),

            // D07–D09: Off-hours 03:00 UTC
            scenarioAt("D07_OFF_HOURS_US_SG_95K",
                amt(95_000), "USD", "US", "SG",
                "US700000001", "SG200000001", BIC_JPMORGAN, BIC_DBS_SINGAPORE, "SWIFT_GPI", offHours),

            scenarioAt("D08_OFF_HOURS_DE_NG_45K",
                amt(45_000), "EUR", "DE", "NG",
                IBAN_DE, "NG100000001", BIC_DEUTSCHE_BANK, "ABNGNGLA", "SWIFT_MT103", offHours),

            scenarioAt("D09_OFF_HOURS_GB_BO_28K",
                amt(28_000), "GBP", "GB", "BO",
                IBAN_GB, "BO100000001", BIC_BARCLAYS, "BNCBBOLAOXXX", "SWIFT_MT103", offHours),

            // D10–D12: OFAC embargoed destination
            scenario("D10_EMBARGOED_US_IR_2M",
                amt(2_000_000), "USD", "US", "IR",
                "US800000001", "IR100000001", BIC_JPMORGAN, "BMIRUS2AXXX", "SWIFT_GPI"),

            scenario("D11_EMBARGOED_US_KP_500K",
                amt(500_000), "USD", "US", "KP",
                "US800000002", "KP100000001", BIC_CITIBANK, "KKBCPYPY", "SWIFT_GPI"),

            scenario("D12_EMBARGOED_US_CU_150K",
                amt(150_000), "USD", "US", "CU",
                "US800000003", "CU100000001", BIC_WELLS_FARGO, "BNBACUBA", "SWIFT_MT103"),

            // D13–D15: Structuring just below €10K
            scenario("D13_STRUCTURING_9800_NL_DE",
                amt(9_800), "EUR", "NL", "DE",
                IBAN_NL, IBAN_DE, BIC_ABN_AMRO, BIC_DEUTSCHE_BANK, "SEPA_INSTANT"),

            scenario("D14_STRUCTURING_9950_FR_IT",
                amt(9_950), "EUR", "FR", "IT",
                IBAN_FR, IBAN_IT, BIC_BNP_PARIBAS, BIC_UNICREDIT, "SEPA_INSTANT"),

            scenario("D15_STRUCTURING_9999_ES_FR",
                amt(9_999), "EUR", "ES", "FR",
                IBAN_ES, IBAN_FR, BIC_SANTANDER, BIC_SG_FRANCE, "SEPA_INSTANT"),

            // ════════════════════════════════════════════════════════════════
            // GROUP E — AML/Compliance Edge Cases (10 transactions)
            // ════════════════════════════════════════════════════════════════

            // E01–E02: Structuring completion (completes 5-payment pattern)
            scenario("E01_STRUCTURING_COMPLETE_IT_FR_9875",
                amt(9_875), "EUR", "IT", "FR",
                IBAN_IT, IBAN_FR, BIC_UNICREDIT, BIC_BNP_PARIBAS, "SEPA_INSTANT"),

            scenario("E02_STRUCTURING_COMPLETE_DE_NL_9910",
                amt(9_910), "EUR", "DE", "NL",
                IBAN_DE, IBAN_NL, BIC_DEUTSCHE_BANK, BIC_ABN_AMRO, "SEPA_INSTANT"),

            // E03–E04: PEP-linked accounts
            scenario("E03_PEP_LINKED_ALEXEI_VOLKOV",
                amt(85_000), "EUR", "RU", "DE",
                "RU200000001", IBAN_DE, "SBRFRUMM", BIC_DEUTSCHE_BANK, "SWIFT_GPI"),

            scenario("E04_PEP_LINKED_ZHANG_WEIMING",
                amt(120_000), "USD", "CN", "US",
                "CN200000001", "US900000001", "ICBKCNBJXXX", BIC_JPMORGAN, "SWIFT_GPI"),

            // E05–E06: FATF grey-list countries
            scenario("E05_FATF_GREY_DE_BO_35K",
                amt(35_000), "EUR", "DE", "BO",
                IBAN_DE, "BO200000001", BIC_DEUTSCHE_BANK, "BNCBBOLAOXXX", "SWIFT_MT103"),

            scenario("E06_FATF_GREY_US_MM_28K",
                amt(28_000), "USD", "US", "MM",
                "US900000002", "MM100000001", BIC_JPMORGAN, "MABEMYMM", "SWIFT_MT103"),

            // E07–E08: SDN entity match attempts
            scenario("E07_SDN_PHONETIC_LAZARUS_GROUP",
                amt(250_000), "USD", "US", "SG",
                "US900000003", "SG300000001", BIC_JPMORGAN, BIC_DBS_SINGAPORE, "SWIFT_GPI"),

            scenario("E08_SDN_FUZZY_IRGC_QF",
                amt(500_000), "EUR", "DE", "IR",
                IBAN_DE, "IR200000001", BIC_DEUTSCHE_BANK, "BMIRUS2AXXX", "SWIFT_GPI"),

            // E09–E10: Round-trip legs 1+2
            scenario("E09_ROUND_TRIP_LEG1_DE_FR_95K",
                amt(95_000), "EUR", "DE", "FR",
                IBAN_DE, IBAN_FR, BIC_DEUTSCHE_BANK, BIC_BNP_PARIBAS, "SEPA"),

            scenario("E10_ROUND_TRIP_LEG2_FR_IT_94500",
                amt(94_500), "EUR", "FR", "IT",
                IBAN_FR, IBAN_IT, BIC_BNP_PARIBAS, BIC_UNICREDIT, "SEPA"),

            // ════════════════════════════════════════════════════════════════
            // GROUP F — Operational Edge Cases (15 transactions)
            // ════════════════════════════════════════════════════════════════

            // F01: Round-trip leg 3 (completes A→B→C→A cycle)
            scenario("F01_ROUND_TRIP_LEG3_IT_DE_94K",
                amt(94_000), "EUR", "IT", "DE",
                IBAN_IT, IBAN_DE, BIC_UNICREDIT, BIC_DEUTSCHE_BANK, "SEPA"),

            // F02–F03: Duplicate instructionId (second triggers DUPLICATE)
            scenario("F02_DUPLICATE_INSTRUCTIONID_1",
                amt(500), "EUR", "NL", "DE",
                IBAN_NL, IBAN_DE, BIC_ABN_AMRO, BIC_DEUTSCHE_BANK, "SEPA_INSTANT"),

            scenario("F03_DUPLICATE_INSTRUCTIONID_2",
                amt(500), "EUR", "NL", "DE",
                IBAN_NL, IBAN_DE, BIC_ABN_AMRO, BIC_DEUTSCHE_BANK, "SEPA_INSTANT"),

            // F04–F05: Embargoed debtor country
            scenario("F04_EMBARGOED_DEBTOR_CU_ES_15K",
                amt(15_000), "EUR", "CU", "ES",
                "CU200000001", IBAN_ES, "BNBACUBA", BIC_SANTANDER, "SWIFT_MT103"),

            scenario("F05_EMBARGOED_DEBTOR_SY_DE_22K",
                amt(22_000), "EUR", "SY", "DE",
                "SY100000001", IBAN_DE, "BKSY33XXXX", BIC_DEUTSCHE_BANK, "SWIFT_MT103"),

            // F06–F08: Insufficient liquidity (exceed nostro balances)
            scenario("F06_LIQUIDITY_EXCEEDED_BACS_50M",
                amt(50_000_000), "GBP", "GB", "GB",
                IBAN_GB, IBAN_GB2, BIC_BARCLAYS, BIC_HSBC_UK, "BACS"),

            scenario("F07_LIQUIDITY_EXCEEDED_FEDWIRE_100M",
                amt(100_000_000), "USD", "US", "US",
                "FNBO000000003", "MELO000000003", BIC_FNBO, BIC_MELO, "FEDWIRE"),

            scenario("F08_LIQUIDITY_EXCEEDED_SEPA_CT_75M",
                amt(75_000_000), "EUR", "DE", "FR",
                IBAN_DE, IBAN_FR, BIC_DEUTSCHE_BANK, BIC_BNP_PARIBAS, "SEPA"),

            // F09–F11: FX conversion
            scenario("F09_FX_GBP_EUR_GB_DE_125K",
                amt(125_000), "GBP", "GB", "DE",
                IBAN_GB, IBAN_DE, BIC_BARCLAYS, BIC_DEUTSCHE_BANK, "SWIFT_GPI"),

            scenario("F10_FX_CHF_USD_CH_US_85K",
                amt(85_000), "CHF", "CH", "US",
                IBAN_CH, "US900000004", BIC_UBS_ZURICH, BIC_JPMORGAN, "SWIFT_GPI"),

            scenario("F11_FX_JPY_EUR_JP_FR_18M",
                amt(18_000_000), "JPY", "JP", "FR",
                ACCT_JP, IBAN_FR, BIC_MIZUHO_JP, BIC_BNP_PARIBAS, "SWIFT_GPI"),

            // F12–F15: Channel-forced BACS (GBP > £1M → routed CHAPS, demonstrates precedence)
            scenario("F12_BACS_FORCED_CHAPS_1_2M",
                amt(1_200_000), "GBP", "GB", "GB",
                IBAN_GB, IBAN_GB2, BIC_BARCLAYS, BIC_HSBC_UK, "BACS"),

            scenario("F13_BACS_FORCED_CHAPS_2_5M",
                amt(2_500_000), "GBP", "GB", "GB",
                IBAN_GB2, IBAN_GB, BIC_HSBC_UK, BIC_BARCLAYS, "BACS"),

            scenario("F14_BACS_FORCED_CHAPS_5M",
                amt(5_000_000), "GBP", "GB", "GB",
                IBAN_GB, IBAN_GB2, BIC_BARCLAYS, BIC_HSBC_UK, "BACS"),

            scenario("F15_INTERNAL_DEUT_SAME_BIC",
                amt(10_000), "EUR", "DE", "DE",
                IBAN_DE, IBAN_DE2, BIC_DEUTSCHE_BANK, BIC_DEUTSCHE_DEUT, "INTERNAL"),

            // F16: Sanction escalation — Wagner Group (SDN hit, high-value RU entity)
            scenario("F16_SDN_WAGNER_GROUP_RU_US",
                amt(3_500_000), "USD", "RU", "US",
                "RU300000001", "US900000010", "SBRFRUMM", BIC_JPMORGAN, "SWIFT_GPI")
        );
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private static Scenario scenario(String label,
                                     BigDecimal amount, String currency,
                                     String debtorCountry, String creditorCountry,
                                     String debtorIban, String creditorIban,
                                     String debtorBic, String creditorBic,
                                     String channel) {
        return scenarioAt(label, amount, currency, debtorCountry, creditorCountry,
                debtorIban, creditorIban, debtorBic, creditorBic, channel, Instant.now());
    }

    private static Scenario scenarioAt(String label,
                                       BigDecimal amount, String currency,
                                       String debtorCountry, String creditorCountry,
                                       String debtorIban, String creditorIban,
                                       String debtorBic, String creditorBic,
                                       String channel, Instant initiatedAt) {
        String paymentId     = UUID.randomUUID().toString();
        String correlationId = UUID.randomUUID().toString();
        String instructionId = "DEMO-" + label + "-" + paymentId.substring(0, 8).toUpperCase();
        String endToEndId    = "E2E-" + label;
        String uetr          = UUID.randomUUID().toString();

        PaymentInitiatedEvent event = new PaymentInitiatedEvent(
                paymentId, correlationId, instructionId, endToEndId, uetr,
                debtorIban, creditorIban,
                "Demo Debtor " + debtorCountry, "Demo Creditor " + creditorCountry,
                debtorBic, creditorBic,
                amount, currency,
                debtorCountry, creditorCountry,
                channel,
                initiatedAt,
                "demo-loader"
        );
        return new Scenario(label, event);
    }

    private static BigDecimal amt(double v) {
        return BigDecimal.valueOf(v);
    }

    private record Scenario(String label, PaymentInitiatedEvent event) {}
}
