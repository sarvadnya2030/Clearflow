package com.clearflow.common.exception;

public class DuplicatePaymentException extends PaymentException {

    public DuplicatePaymentException(String message) {
        super(message);
    }
}
