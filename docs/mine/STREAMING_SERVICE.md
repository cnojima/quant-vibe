# [WIP] Streaming Service Design Document

## Data Source
### Current State
1. daily OHLCV underlying and options bars come from Schwab APIs
  - schwab APIs have limited availability for bars - roughly 1 month back
  - OHCLV deltas are sent in messages, collected and aggregated into 1-min bars
2. historical options OHCLV bar data is collected from a different service, massive.io.
  - the current massive subscription does not provide greeks or volume metadata
3. historical underlying OHCLV bar data is also sourced from massive at 1-min intervals.
4. timescaledb is used for timeseries data.
  - materilized views and continuous aggregate functions create 5-min, 15-min, 1-hour and daily views of the 1-min options bar data.
  - parallel materialized views and continuous aggregate functions are implemented in the underlying_bars table
5. 

## Data Flow

Daily:
STREAMING_SERVICE: during market hours (9:30 - 16:00 EST) schwab streaming API subscribes to UNDERLYING ($SPX) and SPXW options +/- 10% from ATM strikes > 1-min OHCLV bar aggregates > flushed at 60s intervals as published messages for Redis message queue

