# QUANT-VIBE TODOs

## ✅ Refactor backtesting to top-level layer
 - COMPLETE: Moved to `src/backtest/` as peer component
 - Config-driven orchestration via `config/backtest.yaml`
 - CLI: `python scripts/run_backtest.py`

## ✅ Normalize logging format: [datetime][app][level][msg]
 - COMPLETE: Unified logging system in `src/quant_vibe/config/unified_logging.py`
 - Format: `[2025-12-25 12:00:00][app][LEVEL   ] Message`
 - Stack trace handling with proper indentation
 - Multi-line message support
 - Implemented in: backtest ✅, streaming_service ✅
 - Live trading uses custom logging (can be migrated later)

## Refactor live-trading to top-level layer
 - live-trading should piggy-back off of streaming_service instead of re-opening subscriptions
 - API errors flood schwab.  implement a reasonable retry mechanism

## streaming_service
 - implement a reasonable retry mechanism

## Implement notifcations/emails/sms system

## Implement watcher/heartbeat monitoring

## Implement some kind of UI to monitor in realtime, change strategy params, etc.

