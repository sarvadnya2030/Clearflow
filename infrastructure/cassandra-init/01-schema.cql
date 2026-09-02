CREATE KEYSPACE IF NOT EXISTS clearflow
  WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

USE clearflow;

CREATE TABLE IF NOT EXISTS audit_records (
  payment_id TEXT,
  event_time TIMESTAMP,
  id UUID,
  event_type TEXT,
  event_data TEXT,
  correlation_id TEXT,
  service_source TEXT,
  previous_hash TEXT,
  current_hash TEXT,
  block_height BIGINT,
  retention_years INT,
  PRIMARY KEY (payment_id, event_time)
) WITH CLUSTERING ORDER BY (event_time ASC)
  AND default_time_to_live = 220752000;

CREATE TABLE IF NOT EXISTS payment_events (
  payment_id TEXT,
  event_time TIMESTAMP,
  event_type TEXT,
  event_data TEXT,
  service_name TEXT,
  PRIMARY KEY (payment_id, event_time)
) WITH CLUSTERING ORDER BY (event_time ASC);
