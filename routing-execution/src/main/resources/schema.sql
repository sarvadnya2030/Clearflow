CREATE TABLE IF NOT EXISTS nostro_accounts (
    account_id        VARCHAR(36)   NOT NULL PRIMARY KEY,
    currency          VARCHAR(3)    NOT NULL,
    available_balance DECIMAL(18,2) NOT NULL,
    reserved_balance  DECIMAL(18,2) NOT NULL DEFAULT 0,
    version           BIGINT        NOT NULL DEFAULT 0,
    last_updated      TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS liquidity_reservations (
    reservation_id VARCHAR(36)   NOT NULL PRIMARY KEY,
    payment_id     VARCHAR(36)   NOT NULL,
    account_id     VARCHAR(36)   NOT NULL,
    amount         DECIMAL(18,2) NOT NULL,
    currency       VARCHAR(3)    NOT NULL,
    reserved_at    TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    released_at    TIMESTAMP,
    status         VARCHAR(20)   NOT NULL DEFAULT 'RESERVED'
);
