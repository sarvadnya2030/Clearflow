CREATE TABLE payments (
  payment_id VARCHAR2(36) PRIMARY KEY,
  instruction_id VARCHAR2(35) NOT NULL UNIQUE,
  end_to_end_id VARCHAR2(35) NOT NULL,
  uetr VARCHAR2(36),
  debtor_iban_masked VARCHAR2(30),
  debtor_bic VARCHAR2(11),
  debtor_country CHAR(2),
  creditor_iban_masked VARCHAR2(30),
  creditor_bic VARCHAR2(11),
  creditor_country CHAR(2),
  amount NUMBER(20,4) NOT NULL,
  currency CHAR(3) NOT NULL,
  value_date DATE,
  channel VARCHAR2(20),
  status VARCHAR2(20) DEFAULT 'INITIATED',
  correlation_id VARCHAR2(36),
  created_at TIMESTAMP DEFAULT SYSTIMESTAMP,
  updated_at TIMESTAMP DEFAULT SYSTIMESTAMP,
  version NUMBER DEFAULT 0
);

CREATE TABLE ledger_entries (
  id VARCHAR2(36) DEFAULT SYS_GUID() PRIMARY KEY,
  payment_id VARCHAR2(36) NOT NULL,
  account_id VARCHAR2(36) NOT NULL,
  entry_type VARCHAR2(6) NOT NULL CHECK (entry_type IN ('DEBIT','CREDIT')),
  amount NUMBER(20,4) NOT NULL CHECK (amount > 0),
  currency CHAR(3) NOT NULL,
  value_date DATE NOT NULL,
  booking_date TIMESTAMP DEFAULT SYSTIMESTAMP,
  reference VARCHAR2(100),
  correlation_id VARCHAR2(36),
  created_at TIMESTAMP DEFAULT SYSTIMESTAMP,
  version NUMBER DEFAULT 0
);

CREATE TABLE settlement_records (
  id VARCHAR2(36) DEFAULT SYS_GUID() PRIMARY KEY,
  payment_id VARCHAR2(36) NOT NULL UNIQUE,
  rail VARCHAR2(30) NOT NULL,
  status VARCHAR2(20) NOT NULL,
  settled_at TIMESTAMP,
  value_date DATE,
  debtor_iban_masked VARCHAR2(30),
  creditor_iban_masked VARCHAR2(30),
  amount NUMBER(20,4),
  currency CHAR(3),
  correlation_id VARCHAR2(36),
  created_at TIMESTAMP DEFAULT SYSTIMESTAMP,
  updated_at TIMESTAMP DEFAULT SYSTIMESTAMP,
  version NUMBER DEFAULT 0
);

CREATE TABLE nostro_accounts (
  account_id VARCHAR2(36) PRIMARY KEY,
  currency CHAR(3) NOT NULL,
  correspondent_bic VARCHAR2(11),
  available_balance NUMBER(20,4) NOT NULL CHECK (available_balance >= 0),
  reserved_balance NUMBER(20,4) DEFAULT 0 CHECK (reserved_balance >= 0),
  total_balance NUMBER(20,4) GENERATED ALWAYS AS (available_balance + reserved_balance) VIRTUAL,
  last_updated TIMESTAMP DEFAULT SYSTIMESTAMP,
  version NUMBER DEFAULT 0
);

INSERT INTO nostro_accounts(account_id,currency,correspondent_bic,available_balance,reserved_balance,version) VALUES('CLRFLW-EUR-001','EUR','DEUTDEDB',50000000,0,0);
INSERT INTO nostro_accounts(account_id,currency,correspondent_bic,available_balance,reserved_balance,version) VALUES('CLRFLW-USD-001','USD','CHASUS33',50000000,0,0);
INSERT INTO nostro_accounts(account_id,currency,correspondent_bic,available_balance,reserved_balance,version) VALUES('CLRFLW-GBP-001','GBP','BARCGB22',25000000,0,0);
INSERT INTO nostro_accounts(account_id,currency,correspondent_bic,available_balance,reserved_balance,version) VALUES('CLRFLW-CHF-001','CHF','UBSWCHZH',10000000,0,0);
INSERT INTO nostro_accounts(account_id,currency,correspondent_bic,available_balance,reserved_balance,version) VALUES('CLRFLW-JPY-001','JPY','BOTKJPJT',5000000000,0,0);
INSERT INTO nostro_accounts(account_id,currency,correspondent_bic,available_balance,reserved_balance,version) VALUES('CLRFLW-SGD-001','SGD','DBSSSGSG',15000000,0,0);
INSERT INTO nostro_accounts(account_id,currency,correspondent_bic,available_balance,reserved_balance,version) VALUES('CLRFLW-AUD-001','AUD','WPACAU2S',20000000,0,0);
INSERT INTO nostro_accounts(account_id,currency,correspondent_bic,available_balance,reserved_balance,version) VALUES('CLRFLW-CAD-001','CAD','ROYCCAT2',20000000,0,0);
INSERT INTO nostro_accounts(account_id,currency,correspondent_bic,available_balance,reserved_balance,version) VALUES('CLRFLW-HKD-001','HKD','HSBCHKHH',80000000,0,0);
INSERT INTO nostro_accounts(account_id,currency,correspondent_bic,available_balance,reserved_balance,version) VALUES('CLRFLW-SEK-001','SEK','ESSESESS',100000000,0,0);

CREATE TABLE liquidity_reservations (
  reservation_id VARCHAR2(36) DEFAULT SYS_GUID() PRIMARY KEY,
  payment_id VARCHAR2(36) NOT NULL,
  account_id VARCHAR2(36) NOT NULL,
  amount NUMBER(20,4) NOT NULL,
  currency CHAR(3) NOT NULL,
  reserved_at TIMESTAMP DEFAULT SYSTIMESTAMP,
  released_at TIMESTAMP,
  status VARCHAR2(10) DEFAULT 'RESERVED' CHECK (status IN ('RESERVED','RELEASED','EXPIRED'))
);

CREATE TABLE validation_records (
  id VARCHAR2(36) DEFAULT SYS_GUID() PRIMARY KEY,
  payment_id VARCHAR2(36) NOT NULL,
  validation_status VARCHAR2(20),
  rejection_reason VARCHAR2(200),
  iban_valid CHAR(1), bic_valid CHAR(1), currency_valid CHAR(1), embargo_clean CHAR(1),
  validated_at TIMESTAMP, enriched_at TIMESTAMP,
  correlation_id VARCHAR2(36),
  created_at TIMESTAMP DEFAULT SYSTIMESTAMP,
  version NUMBER DEFAULT 0
);

CREATE TABLE screening_results (
  id VARCHAR2(36) DEFAULT SYS_GUID() PRIMARY KEY,
  payment_id VARCHAR2(36) NOT NULL,
  debtor_match_type VARCHAR2(10), debtor_match_score NUMBER(5,4), debtor_matched_entity VARCHAR2(200),
  creditor_match_type VARCHAR2(10), creditor_match_score NUMBER(5,4), creditor_matched_entity VARCHAR2(200),
  overall_result VARCHAR2(10) NOT NULL,
  review_required CHAR(1) DEFAULT 'N',
  screened_at TIMESTAMP DEFAULT SYSTIMESTAMP,
  correlation_id VARCHAR2(36), version NUMBER DEFAULT 0
);

CREATE TABLE correspondent_banks (
  bic VARCHAR2(11) PRIMARY KEY,
  bank_name VARCHAR2(100), country CHAR(2), currency CHAR(3),
  nostro_account VARCHAR2(36), active CHAR(1) DEFAULT 'Y'
);

INSERT INTO correspondent_banks VALUES('DEUTDEDB','Deutsche Bank','DE','EUR','CLRFLW-EUR-001','Y');
INSERT INTO correspondent_banks VALUES('CHASUS33','JP Morgan Chase','US','USD','CLRFLW-USD-001','Y');
INSERT INTO correspondent_banks VALUES('BARCGB22','Barclays Bank','GB','GBP','CLRFLW-GBP-001','Y');
INSERT INTO correspondent_banks VALUES('UBSWCHZH','UBS','CH','CHF','CLRFLW-CHF-001','Y');
INSERT INTO correspondent_banks VALUES('BOTKJPJT','Bank of Tokyo','JP','JPY','CLRFLW-JPY-001','Y');

CREATE TABLE supported_currency_pairs (
  id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  debtor_currency CHAR(3), creditor_currency CHAR(3),
  min_amount NUMBER(20,4) DEFAULT 0.01,
  max_amount NUMBER(20,4) DEFAULT 999999999.99,
  active CHAR(1) DEFAULT 'Y'
);

INSERT INTO supported_currency_pairs(debtor_currency,creditor_currency,active) VALUES('EUR','EUR','Y');
INSERT INTO supported_currency_pairs(debtor_currency,creditor_currency,active) VALUES('USD','USD','Y');
INSERT INTO supported_currency_pairs(debtor_currency,creditor_currency,active) VALUES('GBP','GBP','Y');
INSERT INTO supported_currency_pairs(debtor_currency,creditor_currency,active) VALUES('EUR','USD','Y');
INSERT INTO supported_currency_pairs(debtor_currency,creditor_currency,active) VALUES('USD','EUR','Y');
INSERT INTO supported_currency_pairs(debtor_currency,creditor_currency,active) VALUES('EUR','GBP','Y');
INSERT INTO supported_currency_pairs(debtor_currency,creditor_currency,active) VALUES('GBP','EUR','Y');

CREATE TABLE fx_rates (
  id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  from_currency CHAR(3), to_currency CHAR(3),
  rate NUMBER(20,8), effective_date DATE DEFAULT SYSDATE,
  source VARCHAR2(20) DEFAULT 'STUB'
);

INSERT INTO fx_rates(from_currency,to_currency,rate) VALUES('EUR','USD',1.08000000);
INSERT INTO fx_rates(from_currency,to_currency,rate) VALUES('GBP','USD',1.27000000);
INSERT INTO fx_rates(from_currency,to_currency,rate) VALUES('USD','EUR',0.92500000);
INSERT INTO fx_rates(from_currency,to_currency,rate) VALUES('EUR','EUR',1.00000000);
INSERT INTO fx_rates(from_currency,to_currency,rate) VALUES('USD','USD',1.00000000);
INSERT INTO fx_rates(from_currency,to_currency,rate) VALUES('GBP','GBP',1.00000000);
