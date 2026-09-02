package com.clearflow.routing.service;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.util.Map;
import java.util.UUID;

@Service
public class LiquidityReservationService {

    private final JdbcTemplate jdbcTemplate;

    public LiquidityReservationService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional(isolation = Isolation.READ_COMMITTED, timeout = 10)
    public ReservationResult reserve(String currency, BigDecimal amount, String paymentId, String rail) {
        // Row-level lock: queues concurrent threads instead of causing version-mismatch failures
        var rows = jdbcTemplate.queryForList(
                "SELECT account_id, available_balance FROM nostro_accounts WHERE currency = ? AND available_balance >= ? FETCH FIRST 1 ROWS ONLY FOR UPDATE",
                currency, amount
        );
        if (rows.isEmpty()) {
            throw new InsufficientLiquidityException(currency, amount);
        }

        Map<String, Object> account = rows.get(0);
        String accountId = String.valueOf(account.get("ACCOUNT_ID"));
        BigDecimal available = new BigDecimal(String.valueOf(account.get("AVAILABLE_BALANCE")));

        jdbcTemplate.update(
                "UPDATE nostro_accounts SET available_balance = available_balance - ?, reserved_balance = reserved_balance + ?, version = version + 1, last_updated = CURRENT_TIMESTAMP WHERE account_id = ?",
                amount, amount, accountId
        );

        String reservationId = UUID.randomUUID().toString();
        jdbcTemplate.update(
                "INSERT INTO liquidity_reservations (reservation_id, payment_id, account_id, amount, currency, reserved_at, status) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, 'RESERVED')",
                reservationId, paymentId, accountId, amount, currency
        );

        return new ReservationResult(accountId, reservationId, available, available.subtract(amount));
    }

    @Transactional
    public void release(String paymentId) {
        var rows = jdbcTemplate.queryForList(
                "SELECT account_id, amount FROM liquidity_reservations WHERE payment_id = ? AND status = 'RESERVED'",
                paymentId);
        for (Map<String, Object> row : rows) {
            String accountId = String.valueOf(row.get("ACCOUNT_ID"));
            BigDecimal amount = new BigDecimal(String.valueOf(row.get("AMOUNT")));
            // In dev/sim mode: recycle reserved funds back to available so the pool never drains
            jdbcTemplate.update(
                    "UPDATE nostro_accounts SET available_balance = available_balance + ?, reserved_balance = reserved_balance - ? WHERE account_id = ?",
                    amount, amount, accountId);
            jdbcTemplate.update(
                    "UPDATE liquidity_reservations SET status = 'SETTLED', released_at = CURRENT_TIMESTAMP WHERE payment_id = ?",
                    paymentId);
        }
    }

    /**
     * Read-only lookup of a payment's liquidity reservation state -- no REST
     * path exposed this before (queryable only by direct DB access).
     */
    public Map<String, Object> findByPaymentId(String paymentId) {
        var rows = jdbcTemplate.queryForList(
                "SELECT payment_id, account_id, reservation_id, amount, currency, status, reserved_at, released_at " +
                "FROM liquidity_reservations WHERE payment_id = ? ORDER BY reserved_at DESC FETCH FIRST 1 ROWS ONLY",
                paymentId);
        return rows.isEmpty() ? null : rows.get(0);
    }

    public record ReservationResult(String accountId, String reservationId, BigDecimal nostroBalance, BigDecimal availableAfter) {}
}
