package com.clearflow.audit.domain;

import org.springframework.data.cassandra.core.cql.PrimaryKeyType;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;

import java.time.Instant;

@PrimaryKeyClass
public class AuditRecordKey {
    @PrimaryKeyColumn(name = "payment_id", ordinal = 0, type = PrimaryKeyType.PARTITIONED)
    private String paymentId;
    @PrimaryKeyColumn(name = "event_time", ordinal = 1, type = PrimaryKeyType.CLUSTERED)
    private Instant eventTime;

    public AuditRecordKey() {}
    public AuditRecordKey(String paymentId, Instant eventTime) { this.paymentId = paymentId; this.eventTime = eventTime; }
    public String getPaymentId() { return paymentId; }
    public Instant getEventTime() { return eventTime; }
}
