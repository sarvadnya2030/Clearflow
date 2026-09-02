package com.clearflow.routing.domain;

public enum PaymentRail {
    INTERNAL("Internal Book Transfer", "PT0S", 0),
    SEPA_INSTANT("SEPA Instant Credit Transfer", "PT10S", 1),
    SEPA_CREDIT_TRANSFER("SEPA Credit Transfer", "P1D", 2),
    FASTER_PAYMENTS("UK Faster Payments", "PT2H", 3),
    CHAPS("CHAPS High Value", "PT4H", 4),
    FEDWIRE("Fedwire Funds Service", "PT4H", 5),
    FEDACH("Fed ACH", "P1D", 6),
    CHIPS("CHIPS", "P1D", 7),
    SWIFT_GPI("SWIFT GPI", "P2D", 8),
    SWIFT_MT103("SWIFT MT103", "P3D", 9),
    TARGET2("TARGET2", "P1D", 10),
    BACS("UK BACS", "P3D", 11);

    private final String description;
    private final String expectedSettlementTime;
    private final int priority;

    PaymentRail(String description, String expectedSettlementTime, int priority) {
        this.description = description;
        this.expectedSettlementTime = expectedSettlementTime;
        this.priority = priority;
    }

    public String getDescription() { return description; }
    public String getExpectedSettlementTime() { return expectedSettlementTime; }
    public int getPriority() { return priority; }
}
