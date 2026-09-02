package com.clearflow.compliance.domain;

public record ScreeningResult(
        MatchType matchType,
        double matchScore,
        String matchedEntity,
        String listName,
        String inputName,
        String normalizedInput
) {
    public enum MatchType { EXACT, FUZZY, SOUNDEX, NONE }
}
