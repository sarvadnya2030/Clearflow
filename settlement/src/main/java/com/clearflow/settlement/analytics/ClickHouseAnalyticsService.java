package com.clearflow.settlement.analytics;

import com.clearflow.settlement.domain.SettlementRecord;
import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.SQLException;

/**
 * Writes settlement analytics to ClickHouse for OLAP reporting.
 * Enabled via clearflow.analytics.clickhouse.enabled=true (default in prod, disabled in dev).
 */
@Service
@ConditionalOnProperty(name = "clearflow.analytics.clickhouse.enabled", havingValue = "true")
public class ClickHouseAnalyticsService {

    private static final Logger log = LoggerFactory.getLogger(ClickHouseAnalyticsService.class);

    private static final String CREATE_TABLE = """
        CREATE TABLE IF NOT EXISTS clearflow.settlement_analytics (
            payment_id       String,
            rail             String,
            currency         String,
            amount           Decimal(18, 2),
            debtor_masked    String,
            creditor_masked  String,
            settled_at       DateTime,
            correlation_id   String,
            event_date       Date DEFAULT toDate(settled_at)
        )
        ENGINE = MergeTree()
        PARTITION BY toYYYYMM(event_date)
        ORDER BY (event_date, rail, currency)
        TTL event_date + INTERVAL 7 YEAR;
        """;

    private static final String INSERT_SQL = """
        INSERT INTO clearflow.settlement_analytics
          (payment_id, rail, currency, amount, debtor_masked, creditor_masked, settled_at, correlation_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """;

    @Value("${clearflow.analytics.clickhouse.url:jdbc:clickhouse://localhost:8123/default}")
    private String clickhouseUrl;

    @PostConstruct
    public void initSchema() {
        try (Connection conn = DriverManager.getConnection(clickhouseUrl);
             var stmt = conn.createStatement()) {
            stmt.execute("CREATE DATABASE IF NOT EXISTS clearflow");
            stmt.execute(CREATE_TABLE);
            log.info("ClickHouse settlement_analytics table ready at {}", clickhouseUrl);
        } catch (SQLException e) {
            log.warn("ClickHouse schema init failed (analytics will be skipped): {}", e.getMessage());
        }
    }

    @Async
    public void record(SettlementRecord settlement) {
        try (Connection conn = DriverManager.getConnection(clickhouseUrl);
             PreparedStatement ps = conn.prepareStatement(INSERT_SQL)) {

            ps.setString(1, settlement.getPaymentId());
            ps.setString(2, settlement.getRail());
            ps.setString(3, settlement.getCurrency());
            ps.setBigDecimal(4, settlement.getAmount());
            ps.setString(5, settlement.getDebtorIbanMasked());
            ps.setString(6, settlement.getCreditorIbanMasked());
            ps.setTimestamp(7, java.sql.Timestamp.from(
                settlement.getSettledAt() != null ? settlement.getSettledAt() : java.time.Instant.now()));
            ps.setString(8, settlement.getCorrelationId());
            ps.executeUpdate();

            log.debug("ClickHouse: recorded settlement paymentId={} rail={} amount={} {}",
                settlement.getPaymentId(), settlement.getRail(),
                settlement.getAmount(), settlement.getCurrency());

        } catch (SQLException e) {
            log.warn("ClickHouse record failed for paymentId={}: {}",
                settlement.getPaymentId(), e.getMessage());
        }
    }
}
