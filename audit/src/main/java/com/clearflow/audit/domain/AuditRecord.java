package com.clearflow.audit.domain;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

import java.util.UUID;

@Table("audit_records")
public class AuditRecord {
    @PrimaryKey
    private AuditRecordKey key;
    private UUID id;
    @Column("event_type")
    private String eventType;
    @Column("event_data")
    private String eventData;
    @Column("correlation_id")
    private String correlationId;
    @Column("service_source")
    private String serviceSource;
    @Column("previous_hash")
    private String previousHash;
    @Column("current_hash")
    private String currentHash;
    @Column("block_height")
    private long blockHeight;
    @Column("retention_years")
    private int retentionYears;

    public AuditRecordKey getKey() { return key; }
    public void setKey(AuditRecordKey key) { this.key = key; }
    public UUID getId() { return id; }
    public void setId(UUID id) { this.id = id; }
    public String getEventType() { return eventType; }
    public void setEventType(String eventType) { this.eventType = eventType; }
    public String getEventData() { return eventData; }
    public void setEventData(String eventData) { this.eventData = eventData; }
    public String getCorrelationId() { return correlationId; }
    public void setCorrelationId(String correlationId) { this.correlationId = correlationId; }
    public String getServiceSource() { return serviceSource; }
    public void setServiceSource(String serviceSource) { this.serviceSource = serviceSource; }
    public String getPreviousHash() { return previousHash; }
    public void setPreviousHash(String previousHash) { this.previousHash = previousHash; }
    public String getCurrentHash() { return currentHash; }
    public void setCurrentHash(String currentHash) { this.currentHash = currentHash; }
    public long getBlockHeight() { return blockHeight; }
    public void setBlockHeight(long blockHeight) { this.blockHeight = blockHeight; }
    public int getRetentionYears() { return retentionYears; }
    public void setRetentionYears(int retentionYears) { this.retentionYears = retentionYears; }
}
