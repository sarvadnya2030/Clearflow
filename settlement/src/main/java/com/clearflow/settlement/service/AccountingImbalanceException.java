package com.clearflow.settlement.service;

import java.math.BigDecimal;

public class AccountingImbalanceException extends RuntimeException {
    public AccountingImbalanceException(String paymentId, BigDecimal debits, BigDecimal credits) {
        super("Accounting imbalance for payment " + paymentId + ": debits=" + debits + " credits=" + credits);
    }
}
