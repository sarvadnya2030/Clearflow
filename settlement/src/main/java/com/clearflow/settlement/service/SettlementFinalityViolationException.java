package com.clearflow.settlement.service;

import java.math.BigDecimal;

/**
 * Thrown when settlePayment() is called for a paymentId that is already
 * finalized, with data that doesn't match the original settlement (amount
 * or rail differs). A repeat call with IDENTICAL data is a legitimate
 * idempotent retry and returns the existing record silently -- this
 * exception is specifically for a call that would attempt to change the
 * outcome of a payment past the point settlement-finality allows it.
 */
public class SettlementFinalityViolationException extends RuntimeException {
    public SettlementFinalityViolationException(String paymentId, BigDecimal originalAmount, BigDecimal attemptedAmount) {
        super("Settlement finality violation for payment " + paymentId
                + ": already finalized with amount=" + originalAmount
                + ", attempted re-settlement with amount=" + attemptedAmount);
    }
}
