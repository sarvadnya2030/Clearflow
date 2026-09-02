package com.clearflow.fraud;

import com.clearflow.fraud.domain.FraudRequest;
import com.clearflow.fraud.domain.RiskBand;
import com.clearflow.fraud.service.CountryRiskMatrix;
import com.clearflow.fraud.service.FeatureEngineeringService;
import com.clearflow.fraud.service.FraudScoringService;
import com.clearflow.fraud.service.HeuristicScoringService;
import com.clearflow.fraud.service.LightGBMStubClient;
import com.clearflow.fraud.service.VelocityCheckService;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import reactor.core.publisher.Mono;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

/**
 * Unit tests for FraudScoringService covering the full RiskBand spectrum.
 * Uses real CountryRiskMatrix (FATF-aligned) with mocked velocity + LightGBM.
 */
class FraudScoringServiceTest {

    private CountryRiskMatrix countryRiskMatrix;
    private VelocityCheckService velocity;
    private FraudScoringService service;

    @BeforeEach
    void setUp() {
        countryRiskMatrix = new CountryRiskMatrix();
        velocity = Mockito.mock(VelocityCheckService.class);
        when(velocity.countLast1h(anyString())).thenReturn(1L);
        when(velocity.countLast24h(anyString())).thenReturn(5L);
        when(velocity.isFirstTimePair(anyString(), anyString())).thenReturn(false);

        LightGBMStubClient lgbm = Mockito.mock(LightGBMStubClient.class);
        when(lgbm.predict(any(), anyMap()))
                .thenReturn(Mono.just(new LightGBMStubClient.ModelScoreResponse(0.15d, Map.of("amount", 0.1d), "model-v2")));

        service = new FraudScoringService(
                new FeatureEngineeringService(countryRiskMatrix, velocity),
                lgbm,
                new HeuristicScoringService(countryRiskMatrix, velocity),
                new SimpleMeterRegistry()
        );
    }

    @Test
    @DisplayName("Small domestic EUR (DE→DE, €200) scores LOW via LightGBM model (score < 0.3)")
    void smallDomesticEurIsLow() {
        FraudRequest req = new FraudRequest("p-low-01", "c1",
                "DEUTDEFFXXX", "COBADEFFXXX",
                BigDecimal.valueOf(200), "EUR", "DE", "DE", "SEPA_INSTANT", Instant.now());
        var response = service.score(req);
        assertEquals(RiskBand.LOW, response.riskBand());
        assertTrue(response.fraudScore().doubleValue() < 0.30d);
        assertFalse(response.fallbackUsed(), "LightGBM model should be used for this low-risk request");
    }

    @Test
    @DisplayName("Country risk matrix returns default medium (5) for unknown/null ISO code")
    void unknownCountryDefaultRisk() {
        assertEquals(5, countryRiskMatrix.getRisk("ZZ"));
        assertEquals(5, countryRiskMatrix.getRisk(""));
        assertEquals(5, countryRiskMatrix.getRisk(null));
    }

    @Test
    @DisplayName("FATF grey list country (BO) has risk score 6")
    void fatfGreyListedCountryRisk() {
        assertTrue(countryRiskMatrix.isFatfGreylisted("BO"), "Bolivia must be on FATF grey list");
        assertEquals(6, countryRiskMatrix.getRisk("BO"));
    }

    @Test
    @DisplayName("FATF black list countries (IR, KP, MM) are correctly identified")
    void fatfBlackListedCountries() {
        assertTrue(countryRiskMatrix.isFatfBlacklisted("IR"), "Iran must be FATF black-listed");
        assertTrue(countryRiskMatrix.isFatfBlacklisted("KP"), "North Korea must be FATF black-listed");
        assertTrue(countryRiskMatrix.isFatfBlacklisted("MM"), "Myanmar must be FATF black-listed");
        assertFalse(countryRiskMatrix.isFatfBlacklisted("DE"), "Germany must NOT be FATF black-listed");
        assertEquals(10, countryRiskMatrix.getRisk("IR"), "Iran risk must be maximum (10)");
    }

    @Test
    @DisplayName("High velocity (12 tx/h) escalates score via model (≥ 0.60)")
    void velocityBreachEscalatesScore() {
        when(velocity.countLast1h(anyString())).thenReturn(12L);
        when(velocity.isFirstTimePair(anyString(), anyString())).thenReturn(true);

        LightGBMStubClient lgbm = Mockito.mock(LightGBMStubClient.class);
        when(lgbm.predict(any(), anyMap()))
                .thenReturn(Mono.just(new LightGBMStubClient.ModelScoreResponse(0.71d, Map.of("velocity", 0.8d), "model-v2")));

        FraudScoringService svc = new FraudScoringService(
                new FeatureEngineeringService(countryRiskMatrix, velocity),
                lgbm,
                new HeuristicScoringService(countryRiskMatrix, velocity),
                new SimpleMeterRegistry()
        );
        FraudRequest req = new FraudRequest("p-vel-01", "c1",
                "BARCGB22XXX", "HBUKGB4BXXX",
                BigDecimal.valueOf(15_000), "GBP", "GB", "GB", "FASTER_PAYMENTS", Instant.now());
        var response = svc.score(req);
        assertTrue(response.fraudScore().doubleValue() >= 0.60d,
                "High velocity should push score into HIGH band or above");
    }

    @Test
    @DisplayName("LightGBM circuit open (fallback-cb) activates heuristic scoring")
    void lightGbmFallbackActivatesHeuristic() {
        LightGBMStubClient lgbm = Mockito.mock(LightGBMStubClient.class);
        when(lgbm.predict(any(), anyMap()))
                .thenReturn(Mono.just(new LightGBMStubClient.ModelScoreResponse(0.0d, Map.of(), "fallback-cb")));

        FraudScoringService svc = new FraudScoringService(
                new FeatureEngineeringService(countryRiskMatrix, velocity),
                lgbm,
                new HeuristicScoringService(countryRiskMatrix, velocity),
                new SimpleMeterRegistry()
        );
        FraudRequest req = new FraudRequest("p-fb-01", "c1",
                "INGBNL2AXXX", "ABNANL2AXXX",
                BigDecimal.valueOf(5_000), "EUR", "NL", "NL", "SEPA_CT", Instant.now());
        var response = svc.score(req);
        assertTrue(response.fallbackUsed(), "fallback-cb version must trigger heuristic fallback");
    }

    @Test
    @DisplayName("Large cross-border US→IR (OFAC embargoed) scores CRITICAL with score > 0.85")
    void largeCrossBorderHighRiskIsCritical() {
        when(velocity.countLast1h(anyString())).thenReturn(11L);
        when(velocity.isFirstTimePair(anyString(), anyString())).thenReturn(true);

        LightGBMStubClient lgbm = Mockito.mock(LightGBMStubClient.class);
        when(lgbm.predict(any(), anyMap()))
                .thenReturn(Mono.just(new LightGBMStubClient.ModelScoreResponse(0.91d, Map.of("amount", 0.9d), "model-v1")));

        FraudScoringService svc = new FraudScoringService(
                new FeatureEngineeringService(countryRiskMatrix, velocity),
                lgbm,
                new HeuristicScoringService(countryRiskMatrix, velocity),
                new SimpleMeterRegistry()
        );
        FraudRequest req = new FraudRequest("p-cr-01", "c1",
                "US00TEST", "IR00TEST",
                BigDecimal.valueOf(2_000_000), "USD", "US", "IR", "SWIFT_GPI", Instant.now());
        var response = svc.score(req);
        assertEquals(RiskBand.CRITICAL, response.riskBand());
        assertTrue(response.fraudScore().doubleValue() > 0.85d);
    }
}
