package com.clearflow.compliance.domain;

/**
 * Formal AML decision state for a screened payment. Replaces the previous
 * ad hoc overallResult ∈ {"HIT","CLEAR"} strings, which had no HOLD value
 * and nothing enforcing that a hit actually blocked downstream processing.
 */
public enum AmlState {
    /** No match; payment proceeds immediately. */
    CLEAR,
    /** Fuzzy/Soundex match; held for human review, does not proceed until resolved. */
    HOLD,
    /** Exact match against the sanctions list; held for review, higher priority than HOLD. */
    ESCALATED,
    /** Reviewed and confirmed as a genuine sanctions/embargo hit; terminal, never proceeds. */
    REJECTED
}
