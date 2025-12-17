"""Backtest the Bullish Vertical Put strategy with SPXW options data."""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.backtesting.options_engine import OptionsBacktestEngine
from quant_vibe.strategies.bullish_vertical_put import BullishVerticalPutStrategy
from quant_vibe.data.timescale_store import TimescaleStore


class TeeOutput:
    """Write output to both stdout and a file."""

    def __init__(self, file_path):
        self.terminal = sys.stdout
        self.log = open(file_path, 'w', encoding='utf-8')

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)

    def flush(self):
        self.terminal.flush()
        self.log.flush()

    def close(self):
        self.log.close()
        sys.stdout = self.terminal


def get_date_range():
    """Prompt user to select date range for backtest.

    Returns:
        tuple: (start_date, end_date) as datetime objects
    """
    print("="*70)
    print("SELECT DATE RANGE FOR BACKTEST")
    print("="*70)
    print()
    print("Available date range options:")
    print("  1. Today")
    print("  2. This week (Mon-Sun)")
    print("  3. This month")
    print("  4. This quarter")
    print("  5. This year")
    print("  6. Custom date range")
    print()

    while True:
        choice = input("Enter your choice (1-6): ").strip()

        if choice not in ['1', '2', '3', '4', '5', '6']:
            print("Invalid choice. Please enter a number between 1 and 6.")
            continue

        now = datetime.now()

        if choice == '1':  # Today
            start_date = datetime(now.year, now.month, now.day, 0, 0, 0)
            end_date = datetime(now.year, now.month, now.day, 23, 59, 59)

        elif choice == '2':  # This week (Monday to Sunday)
            # Calculate Monday of current week
            days_since_monday = now.weekday()
            monday = now - timedelta(days=days_since_monday)
            start_date = datetime(monday.year, monday.month, monday.day, 0, 0, 0)

            # Calculate Sunday of current week
            sunday = monday + timedelta(days=6)
            end_date = datetime(sunday.year, sunday.month, sunday.day, 23, 59, 59)

        elif choice == '3':  # This month
            start_date = datetime(now.year, now.month, 1, 0, 0, 0)

            # Calculate last day of month
            if now.month == 12:
                next_month = datetime(now.year + 1, 1, 1)
            else:
                next_month = datetime(now.year, now.month + 1, 1)
            last_day = next_month - timedelta(days=1)
            end_date = datetime(last_day.year, last_day.month, last_day.day, 23, 59, 59)

        elif choice == '4':  # This quarter
            # Q1: Jan-Mar, Q2: Apr-Jun, Q3: Jul-Sep, Q4: Oct-Dec
            quarter = (now.month - 1) // 3 + 1
            quarter_start_month = (quarter - 1) * 3 + 1
            start_date = datetime(now.year, quarter_start_month, 1, 0, 0, 0)

            # Calculate last day of quarter
            quarter_end_month = quarter * 3
            if quarter_end_month == 12:
                next_quarter_start = datetime(now.year + 1, 1, 1)
            else:
                next_quarter_start = datetime(now.year, quarter_end_month + 1, 1)
            last_day = next_quarter_start - timedelta(days=1)
            end_date = datetime(last_day.year, last_day.month, last_day.day, 23, 59, 59)

        elif choice == '5':  # This year
            start_date = datetime(now.year, 1, 1, 0, 0, 0)
            end_date = datetime(now.year, 12, 31, 23, 59, 59)

        elif choice == '6':  # Custom
            print()
            print("Enter custom date range (format: YYYY-MM-DD)")

            while True:
                try:
                    start_str = input("Start date: ").strip()
                    start_parts = start_str.split('-')
                    start_date = datetime(int(start_parts[0]), int(start_parts[1]), int(start_parts[2]), 0, 0, 0)
                    break
                except (ValueError, IndexError):
                    print("Invalid date format. Please use YYYY-MM-DD (e.g., 2025-12-01)")

            while True:
                try:
                    end_str = input("End date: ").strip()
                    end_parts = end_str.split('-')
                    end_date = datetime(int(end_parts[0]), int(end_parts[1]), int(end_parts[2]), 23, 59, 59)

                    if end_date < start_date:
                        print("End date must be after start date. Please try again.")
                        continue
                    break
                except (ValueError, IndexError):
                    print("Invalid date format. Please use YYYY-MM-DD (e.g., 2025-12-15)")

        # Confirm selection
        print()
        print(f"Selected date range: {start_date.date()} to {end_date.date()}")
        confirm = input("Is this correct? (y/n): ").strip().lower()

        if confirm == 'y':
            print()
            return start_date, end_date
        else:
            print()
            print("Let's try again...")
            print()


def main():
    """Run backtest for Bullish Vertical Put strategy."""

    # ========================================================================
    # SETUP OUTPUT LOGGING
    # ========================================================================

    # Create output directory
    output_dir = Path(__file__).parent.parent / "data" / "backtest_results"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create log file with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = output_dir / f"bullish_vertical_put_log_{timestamp}.txt"

    # Redirect stdout to both console and file
    tee = TeeOutput(log_file)
    sys.stdout = tee

    try:
        # ====================================================================
        # DATE SELECTION
        # ====================================================================

        # Get date range from user
        start_date, end_date = get_date_range()

        print("="*70)
        print("BULLISH VERTICAL PUT STRATEGY - BACKTEST")
        print("="*70)
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

        # ====================================================================
        # LOAD DATA
        # ====================================================================

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
            resample_underlying='1min',  # Resample daily bars to 1-minute for intraday simulation
        )

        # ====================================================================
        # DISPLAY DETAILED RESULTS
        # ====================================================================

        print("\n" + "="*70)
        print("DETAILED TRADE LOG")
        print("="*70)

        if not results['trades'].empty:
            trades_df = results['trades']

            for i, trade in trades_df.iterrows():
                # Determine win/loss for emoji
                pnl_emoji = "🟢 WIN" if trade['pnl'] > 0 else "🔴 LOSS" if trade['pnl'] < 0 else "⚪ BREAK-EVEN"

                print(f"\n{'='*70}")
                print(f"TRADE #{i+1} - {pnl_emoji}")
                print(f"{'='*70}")

                # Entry Information
                print(f"\n📥 ENTRY")
                print(f"  Time:     {trade['entry_time'].strftime('%Y-%m-%d %H:%M:%S ET')}")
                print(f"  Trigger:  {trade.get('entry_trigger', 'N/A')}")
                print(f"  SPX @ Entry: ${trade['underlying_entry']:.2f}")

                # Position Details
                print(f"\n📋 POSITION")
                print(f"  Type:     {trade['spread_type']}")

                # Leg details
                if 'legs' in trade and trade['legs']:
                    legs = trade['legs']
                    print(f"  Contracts:")
                    total_premium_paid = 0
                    total_premium_received = 0

                    for leg_idx, leg in enumerate(legs, 1):
                        action = leg['action']
                        qty = leg['quantity']
                        strike = leg['strike_price']
                        entry_price = leg['entry_price']
                        exit_price = leg.get('exit_price', 0)
                        option_type = leg['option_type']

                        # Calculate premium per leg
                        premium_total = entry_price * qty * 100

                        # Track credit/debit
                        if action == 'SELL':
                            total_premium_received += premium_total
                            action_emoji = "📤 SELL"
                        else:
                            total_premium_paid += premium_total
                            action_emoji = "📥 BUY"

                        print(f"    Leg {leg_idx}: {action_emoji} {qty} {option_type} @ ${strike:.2f}")
                        print(f"            Entry: ${entry_price:.2f} x {qty} x 100 = ${premium_total:,.2f}")
                        if exit_price and exit_price > 0:
                            exit_total = exit_price * qty * 100
                            print(f"            Exit:  ${exit_price:.2f} x {qty} x 100 = ${exit_total:,.2f}")

                    # Net Credit/Debit
                    net_credit_debit = total_premium_received - total_premium_paid
                    if net_credit_debit > 0:
                        print(f"\n  💵 Net Credit:  ${net_credit_debit:,.2f} (received)")
                    elif net_credit_debit < 0:
                        print(f"\n  💳 Net Debit:   ${abs(net_credit_debit):,.2f} (paid)")
                    else:
                        print(f"\n  ⚖️  Net:         $0.00 (even)")

                # Exit Information
                print(f"\n📤 EXIT")
                print(f"  Time:     {trade['exit_time'].strftime('%Y-%m-%d %H:%M:%S ET')}")
                print(f"  Duration: {trade['duration_minutes']:.0f} minutes ({trade['duration_minutes']/60:.1f} hours)")
                print(f"  Reason:   {trade['exit_reason']}")
                if trade.get('underlying_exit'):
                    print(f"  SPX @ Exit:  ${trade['underlying_exit']:.2f}")
                    spx_move = trade['underlying_exit'] - trade['underlying_entry']
                    spx_move_pct = (spx_move / trade['underlying_entry']) * 100
                    print(f"  SPX Move:    ${spx_move:+.2f} ({spx_move_pct:+.2f}%)")

                # Performance
                print(f"\n💰 PERFORMANCE")
                print(f"  Entry Cost:   ${trade['entry_cost']:,.2f}")
                print(f"  Exit Value:   ${trade['exit_value']:,.2f}")
                print(f"  Profit/Loss:  ${trade['pnl']:+,.2f} ({trade['pnl_percent']:+.2f}%)")

                # Additional metrics if available
                if trade.get('peak_value'):
                    peak_pnl = trade['peak_value'] - trade['entry_cost']
                    peak_pnl_pct = (peak_pnl / abs(trade['entry_cost'])) * 100 if trade['entry_cost'] != 0 else 0
                    print(f"  Peak P&L:     ${peak_pnl:+,.2f} ({peak_pnl_pct:+.2f}%)")

                    # Profit given back
                    if peak_pnl > trade['pnl']:
                        profit_given_back = peak_pnl - trade['pnl']
                        print(f"  Profit Given Back: ${profit_given_back:,.2f}")

        else:
            print("\n❌ No trades executed during backtest period.")
            print("\nPossible reasons:")
            print("  - Entry conditions not met")
            print("  - Insufficient data for the selected date range")
            print("  - Strategy parameters too restrictive")

        # ====================================================================
        # EDUCATIONAL METRICS
        # ====================================================================

        if not results['trades'].empty:
            print(f"\n{'='*70}")
            print("EDUCATIONAL METRICS & ANALYSIS")
            print(f"{'='*70}")

            trades_df = results['trades']

            # 1. Trade Timing Analysis
            print(f"\n📅 TRADE TIMING ANALYSIS")
            print(f"  Average Hold Time: {trades_df['duration_minutes'].mean():.0f} minutes ({trades_df['duration_minutes'].mean()/60:.1f} hours)")
            print(f"  Shortest Trade:    {trades_df['duration_minutes'].min():.0f} minutes")
            print(f"  Longest Trade:     {trades_df['duration_minutes'].max():.0f} minutes")

            # Entry time distribution
            trades_df['entry_hour'] = pd.to_datetime(trades_df['entry_time']).dt.hour
            print(f"  Most Common Entry Hour: {trades_df['entry_hour'].mode().values[0]}:00 ET")

            # 2. Exit Reason Breakdown
            print(f"\n🚪 EXIT REASON BREAKDOWN")
            exit_counts = trades_df['exit_reason'].value_counts()
            for reason, count in exit_counts.items():
                pct = (count / len(trades_df)) * 100
                print(f"  {reason}: {count} trades ({pct:.1f}%)")

            # 3. Win/Loss Streaks
            print(f"\n📊 WIN/LOSS PATTERNS")
            wins = (trades_df['pnl'] > 0).astype(int)
            current_streak = 1
            max_win_streak = 0
            max_loss_streak = 0
            current_type = None

            for win in wins:
                if win == current_type:
                    current_streak += 1
                else:
                    if current_type == 1:
                        max_win_streak = max(max_win_streak, current_streak)
                    elif current_type == 0:
                        max_loss_streak = max(max_loss_streak, current_streak)
                    current_streak = 1
                    current_type = win

            # Final check
            if current_type == 1:
                max_win_streak = max(max_win_streak, current_streak)
            elif current_type == 0:
                max_loss_streak = max(max_loss_streak, current_streak)

            print(f"  Longest Winning Streak:  {max_win_streak} trades")
            print(f"  Longest Losing Streak:   {max_loss_streak} trades")

            # 4. Risk/Reward Analysis
            print(f"\n⚖️  RISK/REWARD ANALYSIS")
            wins_df = trades_df[trades_df['pnl'] > 0]
            losses_df = trades_df[trades_df['pnl'] < 0]

            if not wins_df.empty and not losses_df.empty:
                avg_win = wins_df['pnl'].mean()
                avg_loss = losses_df['pnl'].mean()
                rr_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0
                print(f"  Average Win:  ${avg_win:,.2f}")
                print(f"  Average Loss: ${avg_loss:,.2f}")
                print(f"  Win/Loss Ratio: {rr_ratio:.2f}:1")

                # Expectancy
                win_rate = len(wins_df) / len(trades_df)
                expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)
                print(f"  Expectancy per Trade: ${expectancy:,.2f}")

            # 5. Drawdown Analysis
            print(f"\n📉 DRAWDOWN ANALYSIS")
            if not results['equity_curve'].empty:
                equity_df = results['equity_curve']
                equity_df['cummax'] = equity_df['portfolio_value'].cummax()
                equity_df['drawdown'] = equity_df['portfolio_value'] - equity_df['cummax']
                equity_df['drawdown_pct'] = (equity_df['drawdown'] / equity_df['cummax']) * 100

                max_dd = equity_df['drawdown'].min()
                max_dd_pct = equity_df['drawdown_pct'].min()
                max_dd_date = equity_df.loc[equity_df['drawdown'].idxmin(), 'timestamp']

                print(f"  Max Drawdown: ${max_dd:,.2f} ({max_dd_pct:.2f}%)")
                print(f"  Max Drawdown Date: {max_dd_date.strftime('%Y-%m-%d %H:%M:%S')}")

            # 6. Profit Distribution
            print(f"\n💵 PROFIT DISTRIBUTION")
            pnl_std = trades_df['pnl'].std()
            print(f"  Median P&L:    ${trades_df['pnl'].median():,.2f}")
            print(f"  Std Dev:       ${pnl_std:,.2f}")
            print(f"  Best Trade:    ${trades_df['pnl'].max():,.2f}")
            print(f"  Worst Trade:   ${trades_df['pnl'].min():,.2f}")

            # Quartiles
            q1 = trades_df['pnl'].quantile(0.25)
            q3 = trades_df['pnl'].quantile(0.75)
            print(f"  25th Percentile: ${q1:,.2f}")
            print(f"  75th Percentile: ${q3:,.2f}")

            # 7. Entry Trigger Analysis
            print(f"\n🎯 ENTRY TRIGGER ANALYSIS")
            if 'entry_trigger' in trades_df.columns:
                # Group by entry trigger and calculate win rate
                trigger_groups = trades_df.groupby('entry_trigger').agg({
                    'pnl': ['count', 'mean', lambda x: (x > 0).sum()]
                })
                trigger_groups.columns = ['count', 'avg_pnl', 'wins']
                trigger_groups['win_rate'] = (trigger_groups['wins'] / trigger_groups['count']) * 100

                for trigger, stats in trigger_groups.iterrows():
                    print(f"  {trigger}:")
                    print(f"    Trades: {int(stats['count'])}, Win Rate: {stats['win_rate']:.1f}%, Avg P&L: ${stats['avg_pnl']:,.2f}")

            # 8. Day of Week Performance (if enough data)
            if len(trades_df) >= 5:
                print(f"\n📆 DAY OF WEEK PERFORMANCE")
                trades_df['day_of_week'] = pd.to_datetime(trades_df['entry_time']).dt.day_name()
                day_performance = trades_df.groupby('day_of_week').agg({
                    'pnl': ['count', 'mean', 'sum', lambda x: (x > 0).sum()]
                })
                day_performance.columns = ['trades', 'avg_pnl', 'total_pnl', 'wins']
                day_performance['win_rate'] = (day_performance['wins'] / day_performance['trades']) * 100

                # Order by day of week
                day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
                day_performance = day_performance.reindex([d for d in day_order if d in day_performance.index])

                for day, stats in day_performance.iterrows():
                    print(f"  {day:9s}: {int(stats['trades'])} trades, {stats['win_rate']:.1f}% win rate, ${stats['avg_pnl']:+,.2f} avg")

            # 9. Return on Capital
            print(f"\n💰 RETURN METRICS")
            total_capital_deployed = trades_df['entry_cost'].abs().sum()
            total_pnl = trades_df['pnl'].sum()
            if total_capital_deployed > 0:
                roi = (total_pnl / total_capital_deployed) * 100
                print(f"  Total Capital Deployed: ${total_capital_deployed:,.2f}")
                print(f"  Total P&L: ${total_pnl:+,.2f}")
                print(f"  ROI on Deployed Capital: {roi:+.2f}%")

            # Annualized return (if we have date range)
            if len(trades_df) > 0:
                first_trade = pd.to_datetime(trades_df['entry_time'].min())
                last_trade = pd.to_datetime(trades_df['exit_time'].max())
                days_traded = (last_trade - first_trade).days
                if days_traded > 0:
                    final_value = initial_capital + total_pnl
                    total_return = (final_value / initial_capital - 1) * 100
                    annualized_return = ((final_value / initial_capital) ** (365 / days_traded) - 1) * 100
                    print(f"  Total Return: {total_return:+.2f}%")
                    print(f"  Annualized Return: {annualized_return:+.2f}% (based on {days_traded} days)")

        # ====================================================================
        # SAVE RESULTS
        # ====================================================================

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

    finally:
        # Close the tee output and restore stdout
        tee.close()
        # Note: print won't work here since stdout is back to terminal
        # But the message is already in the log file


if __name__ == "__main__":
    main()
    # Print final message after logging is closed
    output_dir = Path(__file__).parent.parent / "data" / "backtest_results"
    timestamp_pattern = "bullish_vertical_put_log_*.txt"
    import glob
    log_files = sorted(glob.glob(str(output_dir / timestamp_pattern)))
    if log_files:
        print(f"✅ Complete log saved to: {log_files[-1]}")
