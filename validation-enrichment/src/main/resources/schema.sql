CREATE TABLE IF NOT EXISTS fx_rates (
    from_currency VARCHAR(3) NOT NULL,
    to_currency   VARCHAR(3) NOT NULL,
    rate          DOUBLE     NOT NULL,
    PRIMARY KEY (from_currency, to_currency)
);

CREATE TABLE IF NOT EXISTS routing_rules (
    currency                   VARCHAR(3)  NOT NULL PRIMARY KEY,
    preferred_rail             VARCHAR(50) NOT NULL,
    expected_settlement_hours  INT         NOT NULL
);

CREATE TABLE IF NOT EXISTS correspondent_banks (
    bic    VARCHAR(11)  NOT NULL PRIMARY KEY,
    name   VARCHAR(100) NOT NULL,
    active CHAR(1)      NOT NULL DEFAULT 'Y'
);

CREATE TABLE IF NOT EXISTS supported_currency_pairs (
    debtor_currency   VARCHAR(3)     NOT NULL,
    creditor_currency VARCHAR(3)     NOT NULL,
    active            CHAR(1)        NOT NULL DEFAULT 'Y',
    min_amount        DECIMAL(18,2)  NOT NULL,
    max_amount        DECIMAL(18,2)  NOT NULL,
    PRIMARY KEY (debtor_currency, creditor_currency)
);
