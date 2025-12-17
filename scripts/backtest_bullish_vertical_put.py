"""Backtest the Bullish Vertical Put strategy with SPXW options data."""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.backtesting.options_engine import OptionsBacktestEngine
from quant_vibe.strategies.bullish_vertical_put import BullishVerticalPutStrategy
from quant_vibe.data.timescale_store import TimescaleStore


def main():
    """Run backtest for Bullish Vertical Put strategy."""

    print("="*70)
    print("BULLISH VERTICAL PUT STRATEGY - BACKTEST")
    print("="*70)
    print()

    # ========================================================================
    # CONFIGURATION
    # ========================================================================

    # Date range for backtest
    # Start with a short period to test (1-2 weeks)
    # Data available: 2025-07-01 to 2025-12-12
    start_date = datetime(2025, 12, 15)
    end_date = datetime(2025, 12, 15, 23, 59, 59)  # Include full day of Dec 12

    # Strategy parameters
    spread_width = 10.0  # $10 wide vertical spread
    observation_period = 15  # minutes to watch market open
    pullback_amount = 30.0  # dollar amount for pullback signal
    profit_target_min = 0.2  # 20%
    profit_target_max = 2.0  # 200%
    trailing_stop_pct = 0.20  # 20%
    min_dte = 0  # minimum days to expiration
    max_dte = 0  # maximum days to expiration
    num_spreads = 10  # number of spreads to open per signal

    # Liquidity filters (for data quality)
    min_volume = 50  # minimum volume per contract
    min_bid_ask_spread_pct = 10.0  # maximum 10% bid/ask spread

    # Backtest parameters
    initial_capital = 100000.0

    print(f"Configuration:")
    print(f"  Date Range: {start_date.date()} to {end_date.date()}")
    print(f"  Spread Width: ${spread_width}")
    print(f"  Number of Spreads: {num_spreads}")
    print(f"  Observation Period: {observation_period} minutes")
    print(f"  Pullback: ${pullback_amount}")
    print(f"  Profit Target: {profit_target_min*100}% - {profit_target_max*100}%")
    print(f"  Trailing Stop: {trailing_stop_pct*100}%")
    print(f"  DTE Range: {min_dte} - {max_dte} days")
    print(f"  Liquidity Filters:")
    print(f"    Min Volume: {min_volume}")
    print(f"    Max Bid/Ask Spread: {min_bid_ask_spread_pct}%")
    print(f"  Initial Capital: ${initial_capital:,.2f}")
    print()

    # ========================================================================
    # LOAD DATA
    # ========================================================================

    print("="*70)
    print("LOADING DATA")
    print("="*70)

    # Load data from TimescaleDB
    print("\n1. Loading SPX options data from TimescaleDB...")
    ts_store = TimescaleStore()

    try:
        options_data = ts_store.get_options_for_backtest(
            underlying_ticker='SPX',
            start_time=start_date,
            end_time=end_date,
            min_dte=min_dte,
            max_dte=max_dte,
        )

        if options_data.empty:
            print("❌ No SPX options data found for the specified date range!")
            print(f"   Requested: {start_date.date()} to {end_date.date()}")
            print("\nTroubleshooting:")
            print("  1. Check available data with: SELECT MIN(timestamp), MAX(timestamp) FROM options_bars WHERE underlying_ticker='SPX';")
            print("  2. Verify data collection is complete")
            print("  3. Adjust start_date and end_date in this script")
            return

        print(f"✅ Loaded {len(options_data):,} options bars")
        print(f"   Unique timestamps: {options_data['timestamp'].nunique():,}")
        print(f"   Unique contracts: {options_data['contract_symbol'].nunique():,}")
        print(f"   Date range: {options_data['timestamp'].min()} to {options_data['timestamp'].max()}")
        print(f"   Expirations: {sorted(options_data['expiration_date'].unique())}")

        # Load SPX underlying price estimates from options bid/ask data
        print("\n2. Deriving SPX underlying price from options bid/ask data...")

        underlying_data = ts_store.get_underlying_price_from_options(
            underlying_ticker='SPX',
            start_time=start_date,
            end_time=end_date,
        )

        if underlying_data.empty:
            print("❌ No underlying price data could be derived from options!")
            print("   Check that options data has valid bid/ask prices")
            return

        print(f"✅ Derived {len(underlying_data):,} underlying price estimates")
        print(f"   Date range: {underlying_data.index[0]} to {underlying_data.index[-1]}")
        print(f"   Price range: ${underlying_data['Low'].min():.2f} - ${underlying_data['High'].max():.2f}")
        print(f"   Latest close: ${underlying_data['Close'].iloc[-1]:.2f}")

    except Exception as e:
        print(f"❌ Error loading data: {e}")
        import traceback
        traceback.print_exc()
        return
    finally:
        ts_store.close()

    print()

    # ========================================================================
    # RUN BACKTEST
    # ========================================================================

    # Initialize strategy
    strategy = BullishVerticalPutStrategy(
        spread_width=spread_width,
        observation_period=observation_period,
        pullback_amount=pullback_amount,
        profit_target_min=profit_target_min,
        profit_target_max=profit_target_max,
        trailing_stop_pct=trailing_stop_pct,
        min_dte=min_dte,
        max_dte=max_dte,
        num_spreads=num_spreads,
        min_volume=min_volume,
        min_bid_ask_spread_pct=min_bid_ask_spread_pct,
    )

    # Initialize backtest engine
    engine = OptionsBacktestEngine(
        initial_capital=initial_capital,
        max_positions=1,
        log_trades=True,
    )

    # Run backtest
    results = engine.run(
        strategy=strategy,
        underlying_data=underlying_data,
        options_data=options_data,
        start_date=start_date,
        end_date=end_date,
        resample_underlying='1min',  # Resample daily bars to 1-minute for intraday simulation
    )

    # ========================================================================
    # DISPLAY DETAILED RESULTS
    # ========================================================================

    print("\n" + "="*70)
    print("TRADE DETAILS")
    print("="*70)

    if not results['trades'].empty:
        trades_df = results['trades']

        for i, trade in trades_df.iterrows():
            print(f"\nTrade #{i+1}:")
            print(f"  Entry: {trade['entry_time'].strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"  Exit:  {trade['exit_time'].strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"  Duration: {trade['duration_minutes']:.0f} minutes")
            print(f"  Entry Cost: ${trade['entry_cost']:.2f}")
            print(f"  Exit Value: ${trade['exit_value']:.2f}")
            print(f"  P&L: ${trade['pnl']:+.2f} ({trade['pnl_percent']:+.2f}%)")
            print(f"  Exit Reason: {trade['exit_reason']}")
            print(f"  Underlying @ Entry: ${trade['underlying_entry']:.2f}")
    else:
        print("\nNo trades executed during backtest period.")

    # ========================================================================
    # SAVE RESULTS
    # ========================================================================

    # Save results to CSV
    output_dir = Path(__file__).parent.parent / "data" / "backtest_results"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Save trades
    if not results['trades'].empty:
        trades_file = output_dir / f"bullish_vertical_put_trades_{timestamp}.csv"
        results['trades'].to_csv(trades_file, index=False)
        print(f"\n✅ Trades saved to: {trades_file}")

    # Save equity curve
    if not results['equity_curve'].empty:
        equity_file = output_dir / f"bullish_vertical_put_equity_{timestamp}.csv"
        results['equity_curve'].to_csv(equity_file, index=False)
        print(f"✅ Equity curve saved to: {equity_file}")

    print(f"\n{'='*70}")
    print("BACKTEST COMPLETE")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
