package com.clearflow.fraud.service;

import com.clearflow.fraud.domain.FraudRequest;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Map;

@Service
public class FeatureEngineeringService {

    private final CountryRiskMatrix countryRiskMatrix;
    private final VelocityCheckService velocityCheckService;

    private final Map<String, Integer> currencyRiskMap = Map.of(
            "EUR", 2,
            "USD", 3,
            "GBP", 3,
            "CHF", 2,
            "JPY", 2,
            "SGD", 2,
            "RUB", 8,
            "IRR", 10
    );

    public FeatureEngineeringService(CountryRiskMatrix countryRiskMatrix, VelocityCheckService velocityCheckService) {
        this.countryRiskMatrix = countryRiskMatrix;
        this.velocityCheckService = velocityCheckService;
    }

    public double[] extractFeatures(FraudRequest request) {
        double amountNormalized = Math.log10(request.amount().doubleValue() + 1.0d) / 9.0d;
        double hourOfDay = request.initiatedAt().atZone(java.time.ZoneOffset.UTC).getHour() / 23.0d;
        double dayOfWeekRaw = request.initiatedAt().atZone(java.time.ZoneOffset.UTC).getDayOfWeek().getValue();
        double dayOfWeek = dayOfWeekRaw / 7.0d;
        double isWeekend = dayOfWeekRaw >= 6 ? 1.0d : 0.0d;
        double debtorCountryRisk = countryRiskMatrix.getRisk(request.debtorCountry()) / 10.0d;
        double creditorCountryRisk = countryRiskMatrix.getRisk(request.creditorCountry()) / 10.0d;
        double crossBorder = !request.debtorCountry().equalsIgnoreCase(request.creditorCountry()) ? 1.0d : 0.0d;
        double highRiskCurrencyPair = currencyRiskMap.getOrDefault(request.currency(), 5) / 10.0d;
        double velocity1h = Math.min(100, velocityCheckService.countLast1h(request.debtorIban())) / 100.0d;
        double velocity24h = Math.min(500, velocityCheckService.countLast24h(request.debtorIban())) / 500.0d;
        double isNewCreditorPair = velocityCheckService.isFirstTimePair(request.debtorIban(), request.creditorIban()) ? 1.0d : 0.0d;

        return new double[] {
                amountNormalized,
                hourOfDay,
                dayOfWeek,
                isWeekend,
                debtorCountryRisk,
                creditorCountryRisk,
                crossBorder,
                highRiskCurrencyPair,
                velocity1h,
                velocity24h,
                isNewCreditorPair
        };
    }

    public List<String> featureNames() {
        return List.of(
                "amountNormalized",
                "hourOfDay",
                "dayOfWeek",
                "isWeekend",
                "debtorCountryRisk",
                "creditorCountryRisk",
                "crossBorder",
                "highRiskCurrencyPair",
                "velocityLast1h",
                "velocityLast24h",
                "isNewCreditorPair"
        );
    }
}
