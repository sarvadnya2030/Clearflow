package com.clearflow.fraud.service;

import org.springframework.stereotype.Component;

import java.util.Map;
import java.util.Set;

@Component
public class CountryRiskMatrix {

    private static final Map<String, Integer> RISK_SCORES = Map.ofEntries(
            Map.entry("IR", 10), Map.entry("KP", 10), Map.entry("SY", 10), Map.entry("CU", 10),
            Map.entry("RU", 9), Map.entry("BY", 9), Map.entry("SD", 9), Map.entry("MM", 9),
            Map.entry("NI", 8), Map.entry("VE", 8), Map.entry("AF", 8), Map.entry("IQ", 8),
            Map.entry("LY", 8), Map.entry("SO", 8), Map.entry("YE", 8), Map.entry("ZW", 8),
            Map.entry("CN", 6), Map.entry("PK", 6), Map.entry("NG", 6), Map.entry("UA", 6),
            Map.entry("MX", 4), Map.entry("BR", 4), Map.entry("TR", 4), Map.entry("EG", 4), Map.entry("TH", 4),
            Map.entry("US", 1), Map.entry("GB", 1), Map.entry("DE", 1), Map.entry("FR", 1), Map.entry("NL", 1),
            Map.entry("SE", 1), Map.entry("CH", 1), Map.entry("SG", 1), Map.entry("JP", 1), Map.entry("AU", 1),
            Map.entry("CA", 1), Map.entry("NZ", 1), Map.entry("NO", 1), Map.entry("DK", 1), Map.entry("FI", 1),
            Map.entry("AT", 1), Map.entry("BE", 1), Map.entry("LU", 1)
    );

    /** FATF black list (October 2025 plenary): jurisdictions under increased monitoring with call to action. */
    private static final Set<String> FATF_BLACK = Set.of("IR", "KP", "MM");

    /** FATF grey list (October 2025 plenary): jurisdictions under increased monitoring. */
    private static final Set<String> FATF_GREY = Set.of(
        "DZ", "AO", "BO", "BG", "CM", "CI", "CD", "HT", "KE", "LA",
        "LB", "MC", "NA", "NP", "SS", "SY", "VE", "VN", "VG", "YE"
    );

    public int getRisk(String countryCode) {
        if (countryCode == null || countryCode.isBlank()) {
            return 5;
        }
        String code = countryCode.toUpperCase();
        // FATF grey list countries not already in RISK_SCORES default to 6
        if (FATF_GREY.contains(code) && !RISK_SCORES.containsKey(code)) {
            return 6;
        }
        return RISK_SCORES.getOrDefault(code, 5);
    }

    /** Returns true if the country is on the FATF black list (call-to-action jurisdictions). */
    public boolean isFatfBlacklisted(String countryCode) {
        return countryCode != null && FATF_BLACK.contains(countryCode.toUpperCase());
    }

    /** Returns true if the country is on the FATF grey list (increased monitoring jurisdictions). */
    public boolean isFatfGreylisted(String countryCode) {
        return countryCode != null && FATF_GREY.contains(countryCode.toUpperCase());
    }
}
