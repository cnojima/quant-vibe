-- Migration 011: Add broker account information and multi-account support
-- This migration adds comprehensive account management capabilities
--  Usage:  
--    PGPASSWORD=quantvibe_dev psql -h localhost -U quantvibe -d options_data < src/quant_vibe/data/schema/migrations/011_add_account_info.sql
-- =====================================================
-- REAL TRADING SCHEMA
-- =====================================================

-- Create broker_accounts table in real_trading schema
CREATE TABLE IF NOT EXISTS real_trading.broker_accounts (
    account_hash VARCHAR(255) PRIMARY KEY,
    account_number VARCHAR(20) NOT NULL, -- Masked format: XXX-1234
    nickname VARCHAR(100) NOT NULL,
    account_type VARCHAR(20) NOT NULL CHECK (account_type IN ('MARGIN', 'CASH')),
    is_day_trader BOOLEAN DEFAULT FALSE,
    is_closing_only_restricted BOOLEAN DEFAULT FALSE,
    is_default BOOLEAN DEFAULT FALSE,
    round_trips INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(nickname),
    UNIQUE(account_number)
);

-- Create index for default account lookup
CREATE INDEX idx_real_trading_broker_accounts_default
ON real_trading.broker_accounts(is_default)
WHERE is_default = TRUE;

-- Drop old account_balance table if exists and create enhanced version
DROP TABLE IF EXISTS real_trading.account_balance CASCADE;

CREATE TABLE real_trading.account_balance (
    account_hash VARCHAR(255) NOT NULL REFERENCES real_trading.broker_accounts(account_hash),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Current Balances from Schwab API
    cash_balance DECIMAL(15, 2) NOT NULL DEFAULT 0,
    available_funds DECIMAL(15, 2) NOT NULL DEFAULT 0,
    buying_power DECIMAL(15, 2) NOT NULL DEFAULT 0,
    day_trading_buying_power DECIMAL(15, 2) DEFAULT 0,
    liquidation_value DECIMAL(15, 2) NOT NULL DEFAULT 0,
    long_option_market_value DECIMAL(15, 2) DEFAULT 0,
    short_option_market_value DECIMAL(15, 2) DEFAULT 0,
    maintenance_requirement DECIMAL(15, 2) DEFAULT 0,
    margin_balance DECIMAL(15, 2) DEFAULT 0,
    -- Calculated fields
    portfolio_value DECIMAL(15, 2) NOT NULL DEFAULT 0, -- liquidation_value
    total_pnl DECIMAL(15, 2) NOT NULL DEFAULT 0,
    daily_pnl DECIMAL(15, 2) NOT NULL DEFAULT 0,
    win_rate DECIMAL(5, 2) DEFAULT NULL,
    sharpe_ratio DECIMAL(10, 4) DEFAULT NULL,
    -- Metadata
    is_snapshot BOOLEAN DEFAULT FALSE, -- TRUE for periodic snapshots, FALSE for real-time updates
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (account_hash, timestamp)
);

-- Create hypertable for time-series data
SELECT create_hypertable('real_trading.account_balance', 'timestamp',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE);

-- Create index for account and time lookups
CREATE INDEX idx_real_trading_account_balance_account_time
ON real_trading.account_balance(account_hash, timestamp DESC);

-- Add account_hash to existing tables
ALTER TABLE real_trading.positions
ADD COLUMN IF NOT EXISTS account_hash VARCHAR(255);

ALTER TABLE real_trading.orders
ADD COLUMN IF NOT EXISTS account_hash VARCHAR(255);

-- Create indexes for account filtering
CREATE INDEX IF NOT EXISTS idx_real_trading_positions_account
ON real_trading.positions(account_hash);

CREATE INDEX IF NOT EXISTS idx_real_trading_orders_account
ON real_trading.orders(account_hash);

-- =====================================================
-- PAPER TRADING SCHEMA (Mirror of Real Trading)
-- =====================================================

-- Create broker_accounts table in paper_trading schema
CREATE TABLE IF NOT EXISTS paper_trading.broker_accounts (
    account_hash VARCHAR(255) PRIMARY KEY,
    account_number VARCHAR(20) NOT NULL, -- Masked format: XXX-1234
    nickname VARCHAR(100) NOT NULL,
    account_type VARCHAR(20) NOT NULL CHECK (account_type IN ('MARGIN', 'CASH')),
    is_day_trader BOOLEAN DEFAULT FALSE,
    is_closing_only_restricted BOOLEAN DEFAULT FALSE,
    is_default BOOLEAN DEFAULT FALSE,
    round_trips INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(nickname),
    UNIQUE(account_number)
);

-- Create index for default account lookup
CREATE INDEX idx_paper_trading_broker_accounts_default
ON paper_trading.broker_accounts(is_default)
WHERE is_default = TRUE;

-- Drop old account_balance table if exists and create enhanced version
DROP TABLE IF EXISTS paper_trading.account_balance CASCADE;

CREATE TABLE paper_trading.account_balance (
    account_hash VARCHAR(255) NOT NULL REFERENCES paper_trading.broker_accounts(account_hash),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Current Balances (simulated for paper trading)
    cash_balance DECIMAL(15, 2) NOT NULL DEFAULT 100000, -- Start with 100k
    available_funds DECIMAL(15, 2) NOT NULL DEFAULT 100000,
    buying_power DECIMAL(15, 2) NOT NULL DEFAULT 400000, -- 4x for margin
    day_trading_buying_power DECIMAL(15, 2) DEFAULT 400000,
    liquidation_value DECIMAL(15, 2) NOT NULL DEFAULT 100000,
    long_option_market_value DECIMAL(15, 2) DEFAULT 0,
    short_option_market_value DECIMAL(15, 2) DEFAULT 0,
    maintenance_requirement DECIMAL(15, 2) DEFAULT 0,
    margin_balance DECIMAL(15, 2) DEFAULT 0,
    -- Calculated fields
    portfolio_value DECIMAL(15, 2) NOT NULL DEFAULT 100000,
    total_pnl DECIMAL(15, 2) NOT NULL DEFAULT 0,
    daily_pnl DECIMAL(15, 2) NOT NULL DEFAULT 0,
    win_rate DECIMAL(5, 2) DEFAULT NULL,
    sharpe_ratio DECIMAL(10, 4) DEFAULT NULL,
    -- Metadata
    is_snapshot BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (account_hash, timestamp)
);

-- Create hypertable for time-series data
SELECT create_hypertable('paper_trading.account_balance', 'timestamp',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE);

-- Create index for account and time lookups
CREATE INDEX idx_paper_trading_account_balance_account_time
ON paper_trading.account_balance(account_hash, timestamp DESC);

-- Add account_hash to existing tables
ALTER TABLE paper_trading.positions
ADD COLUMN IF NOT EXISTS account_hash VARCHAR(255);

ALTER TABLE paper_trading.orders
ADD COLUMN IF NOT EXISTS account_hash VARCHAR(255);

-- Create indexes for account filtering
CREATE INDEX IF NOT EXISTS idx_paper_trading_positions_account
ON paper_trading.positions(account_hash);

CREATE INDEX IF NOT EXISTS idx_paper_trading_orders_account
ON paper_trading.orders(account_hash);

-- =====================================================
-- HELPER FUNCTIONS
-- =====================================================

-- Function to ensure only one default account per schema
CREATE OR REPLACE FUNCTION ensure_single_default_account()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.is_default = TRUE THEN
        -- Set all other accounts to non-default
        IF TG_TABLE_SCHEMA = 'real_trading' THEN
            UPDATE real_trading.broker_accounts
            SET is_default = FALSE
            WHERE account_hash != NEW.account_hash;
        ELSIF TG_TABLE_SCHEMA = 'paper_trading' THEN
            UPDATE paper_trading.broker_accounts
            SET is_default = FALSE
            WHERE account_hash != NEW.account_hash;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create triggers for both schemas
CREATE TRIGGER ensure_single_default_real
BEFORE INSERT OR UPDATE ON real_trading.broker_accounts
FOR EACH ROW
WHEN (NEW.is_default = TRUE)
EXECUTE FUNCTION ensure_single_default_account();

CREATE TRIGGER ensure_single_default_paper
BEFORE INSERT OR UPDATE ON paper_trading.broker_accounts
FOR EACH ROW
WHEN (NEW.is_default = TRUE)
EXECUTE FUNCTION ensure_single_default_account();

-- Function to update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create update triggers for broker_accounts
CREATE TRIGGER update_real_broker_accounts_updated_at
BEFORE UPDATE ON real_trading.broker_accounts
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_paper_broker_accounts_updated_at
BEFORE UPDATE ON paper_trading.broker_accounts
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

-- =====================================================
-- DATA MIGRATION
-- =====================================================

-- Note: After running this migration, you'll need to:
-- 1. Run the live trading engine to populate broker_accounts from Schwab
-- 2. Update existing positions/orders with the correct account_hash
-- 3. Set a default account for each schema