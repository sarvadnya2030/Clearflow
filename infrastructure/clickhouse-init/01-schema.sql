CREATE DATABASE IF NOT EXISTS clearflow;

CREATE TABLE IF NOT EXISTS clearflow.payment_analytics (
  payment_id String,
  rail LowCardinality(String),
  currency LowCardinality(String),
  debtor_country LowCardinality(String),
  creditor_country LowCardinality(String),
  amount_usd Float64,
  fraud_score Float32,
  aml_result LowCardinality(String),
  settlement_latency_ms UInt32,
  settled_at DateTime,
  hour UInt8,
  day_of_week UInt8,
  month UInt8,
  year UInt16
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(settled_at)
ORDER BY (settled_at, rail, currency)
TTL settled_at + INTERVAL 7 YEAR;

CREATE TABLE IF NOT EXISTS clearflow.fraud_analytics (
  payment_id String,
  fraud_score Float32,
  risk_band LowCardinality(String),
  model_version String,
  debtor_country LowCardinality(String),
  creditor_country LowCardinality(String),
  amount Float64,
  currency LowCardinality(String),
  fallback_used UInt8,
  scored_at DateTime
) ENGINE = MergeTree()
ORDER BY (scored_at, risk_band);

CREATE MATERIALIZED VIEW IF NOT EXISTS clearflow.hourly_payment_stats
ENGINE = SummingMergeTree()
ORDER BY (hour, rail, currency)
AS SELECT
  toHour(settled_at) AS hour,
  rail, currency,
  count() AS payment_count,
  sum(amount_usd) AS total_volume_usd,
  avg(settlement_latency_ms) AS avg_latency_ms
FROM clearflow.payment_analytics
GROUP BY hour, rail, currency;
