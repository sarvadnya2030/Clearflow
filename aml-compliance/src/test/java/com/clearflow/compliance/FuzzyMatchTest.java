package com.clearflow.compliance;

import com.clearflow.compliance.domain.ScreeningResult;
import com.clearflow.compliance.service.FuzzyScreeningEngine;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

/**
 * AML name screening tests for the FuzzyScreeningEngine.
 * Covers exact match, Jaro-Winkler fuzzy, Unicode NFD normalisation, and Soundex phonetics.
 */
class FuzzyMatchTest {

    private final FuzzyScreeningEngine engine = new FuzzyScreeningEngine();

    @Test
    @DisplayName("Exact match returns EXACT with score 1.0")
    void exactMatch() {
        ScreeningResult result = engine.screenName("JOHN SMITH", List.of("JOHN SMITH"), 0.85);
        assertEquals(ScreeningResult.MatchType.EXACT, result.matchType());
        assertEquals(1.0d, result.matchScore());
    }

    @Test
    @DisplayName("Token-sort canonicalises reversed names (SMITH JOHN → JOHN SMITH)")
    void tokenSort() {
        ScreeningResult result = engine.screenName("SMITH JOHN", List.of("JOHN SMITH"), 0.85);
        assertEquals(ScreeningResult.MatchType.EXACT, result.matchType(),
                "Token sort must canonicalise name order before comparison");
    }

    @Test
    @DisplayName("Unicode NFD: MÜLLER matches MULLER after diacritic stripping")
    void unicodeNfdDiacritics() {
        ScreeningResult result = engine.screenName("MÜLLER HANS", List.of("MULLER HANS"), 0.85);
        assertEquals(ScreeningResult.MatchType.EXACT, result.matchType(),
                "NFD normalisation must strip Ü → U before comparison");
    }

    @Test
    @DisplayName("Jaro-Winkler fuzzy: AL QAIDA NETWORK ≈ AL QAIDA NETWORC (one char diff)")
    void fuzzyMatch() {
        ScreeningResult result = engine.screenName("AL QAIDA NETWORK", List.of("AL QAIDA NETWORC"), 0.85);
        assertEquals(ScreeningResult.MatchType.FUZZY, result.matchType());
        assertTrue(result.matchScore() > 0.85d);
    }

    @Test
    @DisplayName("OFAC near-miss: LAZURUS GROUP fuzzy-matches LAZARUS GROUP")
    void lazarusGroupNearMiss() {
        ScreeningResult result = engine.screenName("LAZURUS GROUP", List.of("LAZARUS GROUP"), 0.85);
        assertNotEquals(ScreeningResult.MatchType.NONE, result.matchType(),
                "LAZURUS should match LAZARUS via Jaro-Winkler or Soundex");
        assertTrue(result.matchScore() > 0.80d);
    }

    @Test
    @DisplayName("Soundex phonetic: KHALID matches KHALED (both encode to K430)")
    void soundexPhoneticMatch() {
        // Single-token names: after canonicalize() first tokens differ (KHALID ≠ KHALED),
        // JW(0.911) < threshold(0.99), so Soundex path is reached.
        // Soundex("KHALID") = Soundex("KHALED") = K430 → SOUNDEX match.
        ScreeningResult result = engine.screenName(
                "KHALID", List.of("KHALED"), 0.99);
        assertEquals(ScreeningResult.MatchType.SOUNDEX, result.matchType(),
                "KHALID/KHALED share Soundex K430 — phonetic match expected");
    }

    @Test
    @DisplayName("Below-threshold returns NONE (JANE DOE vs JANE DOX at 0.95)")
    void thresholdBoundary() {
        ScreeningResult low = engine.screenName("JANE DOE", List.of("JANE DOX"), 0.95);
        assertEquals(ScreeningResult.MatchType.NONE, low.matchType());
    }
}
