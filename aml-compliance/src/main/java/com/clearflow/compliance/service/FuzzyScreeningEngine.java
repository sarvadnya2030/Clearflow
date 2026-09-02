package com.clearflow.compliance.service;

import com.clearflow.compliance.domain.ScreeningResult;
import org.apache.commons.codec.language.Soundex;
import org.apache.commons.text.similarity.JaroWinklerSimilarity;
import org.springframework.stereotype.Component;

import java.text.Normalizer;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

@Component
public class FuzzyScreeningEngine {

    private final JaroWinklerSimilarity jaroWinkler = new JaroWinklerSimilarity();
    private final Soundex soundex = new Soundex();

    public ScreeningResult screenName(String inputName, List<String> sanctionedNames, double threshold) {
        String normalizedInput = canonicalize(normalize(inputName));

        for (String sanctionedName : sanctionedNames) {
            String normalizedSanctioned = canonicalize(normalize(sanctionedName));
            if (normalizedInput.equals(normalizedSanctioned)) {
                return new ScreeningResult(ScreeningResult.MatchType.EXACT, 1.0d, sanctionedName, "SDN", inputName, normalizedInput);
            }
        }

        for (String sanctionedName : sanctionedNames) {
            String normalizedSanctioned = canonicalize(normalize(sanctionedName));
            Double score = jaroWinkler.apply(normalizedInput, normalizedSanctioned);
            if (score != null && score >= threshold) {
                return new ScreeningResult(ScreeningResult.MatchType.FUZZY, score, sanctionedName, "SDN", inputName, normalizedInput);
            }
        }

        String inputFirst = firstToken(normalizedInput);
        for (String sanctionedName : sanctionedNames) {
            String sanctionedFirst = firstToken(canonicalize(normalize(sanctionedName)));
            if (!inputFirst.isBlank() && inputFirst.equals(sanctionedFirst)) {
                continue;
            }
            if (!inputFirst.isBlank() && !sanctionedFirst.isBlank() && soundex.encode(inputFirst).equals(soundex.encode(sanctionedFirst))) {
                double score = jaroWinkler.apply(normalizedInput, canonicalize(normalize(sanctionedName)));
                if (score >= threshold) {
                    return new ScreeningResult(ScreeningResult.MatchType.SOUNDEX, score, sanctionedName, "SDN", inputName, normalizedInput);
                }
            }
        }

        return new ScreeningResult(ScreeningResult.MatchType.NONE, 0.0d, null, "SDN", inputName, normalizedInput);
    }

    public ScreeningResult screenPayment(String debtorName, String creditorName, List<String> sanctionedNames, double threshold) {
        ScreeningResult debtor = screenName(debtorName, sanctionedNames, threshold);
        ScreeningResult creditor = screenName(creditorName, sanctionedNames, threshold);
        return debtor.matchScore() >= creditor.matchScore() ? debtor : creditor;
    }

    private String normalize(String name) {
        String nfd = Normalizer.normalize(name == null ? "" : name, Normalizer.Form.NFD);
        return nfd.replaceAll("\\p{M}", "").toUpperCase().trim().replaceAll("\\s+", " ");
    }

    private String canonicalize(String normalized) {
        return Arrays.stream(normalized.split(" ")).filter(s -> !s.isBlank()).sorted(Comparator.naturalOrder()).reduce((a, b) -> a + " " + b).orElse("");
    }

    private String firstToken(String name) {
        if (name == null || name.isBlank()) return "";
        String[] parts = name.split(" ");
        return parts.length > 0 ? parts[0] : "";
    }
}
