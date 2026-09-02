package com.clearflow.fraud.service;

import com.clearflow.fraud.domain.FraudRequest;
import com.clearflow.fraud.domain.FraudResponse;
import com.clearflow.fraud.domain.RiskBand;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;
import java.util.Map;

/**
 * Multi-factor heuristic fraud scorer.
 *
 * Designed to give a realistic distribution over clean EU/US payments:
 *   ~60% LOW  (0.00–0.19)
 *   ~22% MEDIUM (0.20–0.39)
 *   ~12% HIGH  (0.40–0.59)
 *   ~6%  CRITICAL (≥0.60)
 *
 * Signal weights are calibrated against typical financial-crime typologies:
 *   - Sanctions/FATF exposure (largest weight — clear regulatory trigger)
 *   - Amount thresholds (CTR/SAR-style bands)
 *   - Cross-border + high-risk channel combo
 *   - Velocity (unusual burst from single IBAN)
 *   - First-time counterparty + large amount (new-relationship risk)
 *   - Structuring pattern (just-below round-number amounts)
 */
@Service
public class HeuristicScoringService {

    private final CountryRiskMatrix countryRiskMatrix;
    private final VelocityCheckService velocityCheckService;

    @Value("${fraud.velocity.threshold.1h:5}")
    private long velocityThreshold1h;

    @Value("${fraud.velocity.threshold.24h:20}")
    private long velocityThreshold24h;

    public HeuristicScoringService(CountryRiskMatrix countryRiskMatrix,
                                   VelocityCheckService velocityCheckService) {
        this.countryRiskMatrix    = countryRiskMatrix;
        this.velocityCheckService = velocityCheckService;
    }

    public FraudResponse heuristicScore(FraudRequest request, long startedAt) {
        double score = 0.0;

        int debtorRisk   = countryRiskMatrix.getRisk(request.debtorCountry());
        int creditorRisk = countryRiskMatrix.getRisk(request.creditorCountry());
        boolean crossBorder = !request.debtorCountry().equalsIgnoreCase(request.creditorCountry());

        long velocity1h  = velocityCheckService.countLast1h(request.debtorIban());
        long velocity24h = velocityCheckService.countLast24h(request.debtorIban());
        boolean firstPair = velocityCheckService.isFirstTimePair(request.debtorIban(), request.creditorIban());

        double amount = request.amount().doubleValue();

        // ── 1. Sanctions / FATF exposure (highest weight) ──────────────────
        if (debtorRisk >= 10 || creditorRisk >= 10) {
            score += 0.55;   // FATF black-list: Iran, DPRK, Myanmar → near-CRITICAL
        } else if (debtorRisk >= 9 || creditorRisk >= 9) {
            score += 0.40;   // Russia, Belarus, Sudan → HIGH
        } else if (debtorRisk >= 8 || creditorRisk >= 8) {
            score += 0.25;   // Venezuela, Afghanistan, Yemen, Libya … → MEDIUM-HIGH
        } else if (debtorRisk >= 6 || creditorRisk >= 6) {
            score += 0.12;   // FATF grey-list / elevated monitoring
        } else if (debtorRisk >= 4 || creditorRisk >= 4) {
            score += 0.05;   // Mexico, Brazil, Turkey … → small uplift
        }

        // ── 2. Amount thresholds (CTR/SAR style) ───────────────────────────
        if (amount >= 500_000)       score += 0.18;   // >500K → report territory
        else if (amount >= 100_000)  score += 0.10;   // >100K
        else if (amount >= 50_000)   score += 0.05;   // >50K
        else if (amount >= 10_000)   score += 0.02;   // >10K

        // ── 3. Structuring signal (just below common CTR thresholds) ────────
        if ((amount > 9_000 && amount < 10_000) ||
            (amount > 4_500 && amount < 5_000)  ||
            (amount > 9_800 && amount < 10_000)) {
            score += 0.12;   // classic structuring pattern
        }

        // ── 4. Cross-border + high-risk channel combo ──────────────────────
        String ch = request.channel() == null ? "" : request.channel().toUpperCase();
        if (crossBorder && ("SWIFT_GPI".equals(ch) || "FEDWIRE".equals(ch))) {
            score += 0.06;
        }
        if (crossBorder && amount >= 50_000) {
            score += 0.04;   // large cross-border wire
        }

        // ── 5. Velocity (burst from single IBAN) ───────────────────────────
        if (velocity1h > velocityThreshold1h * 4)       score += 0.15;
        else if (velocity1h > velocityThreshold1h * 2)  score += 0.08;
        else if (velocity1h > velocityThreshold1h)      score += 0.04;

        if (velocity24h > velocityThreshold24h * 3)     score += 0.10;

        // ── 6. First-time counterparty + large amount ──────────────────────
        if (firstPair && amount >= 100_000) score += 0.12;
        else if (firstPair && amount >= 50_000) score += 0.06;

        // ── 7. Currency risk ────────────────────────────────────────────────
        String currency = request.currency() == null ? "" : request.currency().toUpperCase();
        if ("USD".equals(currency) && crossBorder && creditorRisk >= 6) score += 0.04;

        // Cap at 0.95 — reserve 1.0 for confirmed model output only
        double bounded = Math.min(score, 0.95);
        BigDecimal finalScore = BigDecimal.valueOf(bounded).setScale(4, RoundingMode.HALF_UP);

        return new FraudResponse(
                request.paymentId(),
                finalScore,
                toRiskBand(finalScore),
                Map.of("heuristic", 1.0d),
                "heuristic-v2",
                Instant.now(),
                System.currentTimeMillis() - startedAt,
                true
        );
    }

    public RiskBand toRiskBand(BigDecimal score) {
        double v = score.doubleValue();
        if (v < 0.20) return RiskBand.LOW;
        if (v < 0.40) return RiskBand.MEDIUM;
        if (v < 0.60) return RiskBand.HIGH;
        return RiskBand.CRITICAL;
    }
}
