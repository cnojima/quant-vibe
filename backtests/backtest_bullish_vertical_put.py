"""Backtest the Bullish Vertical Put strategy with SPXW options data."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.config.logging_config import setup_logging
from quant_vibe.backtesting import BacktestReporter, OptionsBacktestEngine
from quant_vibe.strategies.bullish_vertical_put import BullishVerticalPutStrategy
from quant_vibe.utils import (
    get_date_range,
    load_options_backtest_data,
    save_backtest_results,
    setup_backtest_output,
)


def main():
    """Run backtest for Bullish Vertical Put strategy."""
    setup_logging()

    # ========================================================================
    # SETUP OUTPUT LOGGING
    # ========================================================================

    output_dir, timestamp, tee = setup_backtest_output("bullish_vertical_put")
    sys.stdout = tee

    try:
        # ====================================================================
        # DATE SELECTION
        # ====================================================================

        start_date, end_date = get_date_range()

        print("=" * 70)
        print("BULLISH VERTICAL PUT STRATEGY - BACKTEST")
        print("=" * 70)
        print()

        # ====================================================================
        # CONFIGURATION
        # ====================================================================

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

        print("Configuration:")
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

        # ====================================================================
        # LOAD DATA
        # ====================================================================

        options_data, underlying_data = load_options_backtest_data(
            underlying_ticker="SPX",
            start_date=start_date,
            end_date=end_date,
            min_dte=min_dte,
            max_dte=max_dte,
            # db_profile auto-detected from USE_REMOTE_TIMESCALE env var
        )

        # ====================================================================
        # RUN BACKTEST
        # ====================================================================

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
            resample_underlying="1min",
        )

        # ====================================================================
        # DISPLAY RESULTS
        # ====================================================================

        reporter = BacktestReporter()
        reporter.print_trade_details(results["trades"])
        reporter.print_educational_metrics(
            results["trades"],
            results["equity_curve"],
            initial_capital,
        )

        # ====================================================================
        # SAVE RESULTS
        # ====================================================================

        save_backtest_results(
            results=results,
            strategy_name="bullish_vertical_put",
            output_dir=output_dir,
            timestamp=timestamp,
        )

        print(f"\n{'=' * 70}")
        print("BACKTEST COMPLETE")
        print(f"{'=' * 70}\n")

    finally:
        # Close the tee output and restore stdout
        tee.close()


if __name__ == "__main__":
    main()
    # Print final message after logging is closed
    output_dir = Path(__file__).parent.parent / "backtests" / "backtest_results"
    timestamp_pattern = "bullish_vertical_put_log_*.txt"
    import glob

    log_files = sorted(glob.glob(str(output_dir / timestamp_pattern)))
    if log_files:
        print(f"✅ Complete log saved to: {log_files[-1]}")
