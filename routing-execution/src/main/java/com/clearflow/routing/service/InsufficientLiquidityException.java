package com.clearflow.routing.service;

import java.math.BigDecimal;

public class InsufficientLiquidityException extends RuntimeException {
    public InsufficientLiquidityException(String currency, BigDecimal amount) {
        super("Insufficient liquidity for currency=" + currency + " amount=" + amount);
    }
}
