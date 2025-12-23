"""Backtest results reporting and analytics."""

from typing import Dict

import pandas as pd


class BacktestReporter:
    """Generate detailed reports and analytics for backtest results.

    This class provides methods to display trade details, educational metrics,
    and comprehensive analytics for options backtest results.

    Example:
        ```python
        reporter = BacktestReporter()
        reporter.print_trade_details(results['trades'])
        reporter.print_educational_metrics(
            results['trades'],
            results['equity_curve'],
            initial_capital=100000.0
        )
        ```
    """

    def print_trade_details(self, trades_df: pd.DataFrame) -> None:
        """Print detailed trade-by-trade analysis.

        Args:
            trades_df: DataFrame of trades from backtest results

        Displays:
            - Entry/exit information
            - Position details (legs, strikes, premiums)
            - Performance metrics
            - Win/loss indication
        """
        print("\n" + "=" * 70)
        print("DETAILED TRADE LOG")
        print("=" * 70)

        if trades_df.empty:
            print("\n❌ No trades executed during backtest period.")
            print("\nPossible reasons:")
            print("  - Entry conditions not met")
            print("  - Insufficient data for the selected date range")
            print("  - Strategy parameters too restrictive")
            return

        for i, trade in trades_df.iterrows():
            # Determine win/loss for emoji
            if trade["pnl"] > 0:
                pnl_emoji = "🟢 WIN"
            elif trade["pnl"] < 0:
                pnl_emoji = "🔴 LOSS"
            else:
                pnl_emoji = "⚪ BREAK-EVEN"

            print(f"\n{'=' * 70}")
            print(f"TRADE #{i+1} - {pnl_emoji}")
            print(f"{'=' * 70}")

            # Entry Information
            print("\n📥 ENTRY")
            print(f"  Time:     {trade['entry_time'].strftime('%Y-%m-%d %H:%M:%S ET')}")
            print(f"  Trigger:  {trade.get('entry_trigger', 'N/A')}")
            print(f"  SPX @ Entry: ${trade['underlying_entry']:.2f}")

            # Position Details
            print("\n📋 POSITION")
            print(f"  Type:     {trade['spread_type']}")

            # Leg details
            if "legs" in trade and trade["legs"]:
                legs = trade["legs"]
                print("  Contracts:")
                total_premium_paid = 0
                total_premium_received = 0

                for leg_idx, leg in enumerate(legs, 1):
                    action = leg["action"]
                    qty = leg["quantity"]
                    strike = leg["strike_price"]
                    entry_price = leg["entry_price"]
                    exit_price = leg.get("exit_price", 0)
                    option_type = leg["option_type"]

                    # Calculate premium per leg
                    premium_total = entry_price * qty * 100

                    # Track credit/debit
                    if action == "SELL":
                        total_premium_received += premium_total
                        action_emoji = "📤 SELL"
                    else:
                        total_premium_paid += premium_total
                        action_emoji = "📥 BUY"

                    print(
                        f"    Leg {leg_idx}: {action_emoji} {qty} {option_type} @ " f"${strike:.2f}"
                    )
                    print(
                        f"            Entry: ${entry_price:.2f} x {qty} x 100 = "
                        f"${premium_total:,.2f}"
                    )
                    if exit_price and exit_price > 0:
                        exit_total = exit_price * qty * 100
                        print(
                            f"            Exit:  ${exit_price:.2f} x {qty} x 100 = "
                            f"${exit_total:,.2f}"
                        )

                # Net Credit/Debit
                net_credit_debit = total_premium_received - total_premium_paid
                if net_credit_debit > 0:
                    print(f"\n  💵 Net Credit:  ${net_credit_debit:,.2f} (received)")
                elif net_credit_debit < 0:
                    print(f"\n  💳 Net Debit:   ${abs(net_credit_debit):,.2f} (paid)")
                else:
                    print("\n  ⚖️  Net:         $0.00 (even)")

            # Exit Information
            print("\n📤 EXIT")
            print(f"  Time:     {trade['exit_time'].strftime('%Y-%m-%d %H:%M:%S ET')}")
            print(
                f"  Duration: {trade['duration_minutes']:.0f} minutes "
                f"({trade['duration_minutes']/60:.1f} hours)"
            )
            print(f"  Reason:   {trade['exit_reason']}")
            if trade.get("underlying_exit"):
                print(f"  SPX @ Exit:  ${trade['underlying_exit']:.2f}")
                spx_move = trade["underlying_exit"] - trade["underlying_entry"]
                spx_move_pct = (spx_move / trade["underlying_entry"]) * 100
                print(f"  SPX Move:    ${spx_move:+.2f} ({spx_move_pct:+.2f}%)")

            # Performance
            print("\n💰 PERFORMANCE")
            print(f"  Entry Cost:   ${trade['entry_cost']:,.2f}")
            print(f"  Exit Value:   ${trade['exit_value']:,.2f}")
            print(f"  Profit/Loss:  ${trade['pnl']:+,.2f} ({trade['pnl_percent']:+.2f}%)")

            # Additional metrics if available
            if trade.get("peak_value"):
                peak_pnl = trade["peak_value"] - trade["entry_cost"]
                peak_pnl_pct = (
                    (peak_pnl / abs(trade["entry_cost"])) * 100 if trade["entry_cost"] != 0 else 0
                )
                print(f"  Peak P&L:     ${peak_pnl:+,.2f} ({peak_pnl_pct:+.2f}%)")

                # Profit given back
                if peak_pnl > trade["pnl"]:
                    profit_given_back = peak_pnl - trade["pnl"]
                    print(f"  Profit Given Back: ${profit_given_back:,.2f}")

    def print_educational_metrics(
        self,
        trades_df: pd.DataFrame,
        equity_curve: pd.DataFrame,
        initial_capital: float,
    ) -> None:
        """Print comprehensive educational metrics and analysis.

        Args:
            trades_df: DataFrame of trades from backtest results
            equity_curve: DataFrame of equity curve from backtest results
            initial_capital: Initial capital used in backtest

        Displays:
            - Trade timing analysis
            - Exit reason breakdown
            - Win/loss patterns and streaks
            - Risk/reward analysis
            - Drawdown analysis
            - Profit distribution
            - Entry trigger analysis
            - Day of week performance
            - Return metrics
        """
        if trades_df.empty:
            return

        print(f"\n{'=' * 70}")
        print("EDUCATIONAL METRICS & ANALYSIS")
        print(f"{'=' * 70}")

        # 1. Trade Timing Analysis
        print("\n📅 TRADE TIMING ANALYSIS")
        avg_duration = trades_df["duration_minutes"].mean()
        print(f"  Average Hold Time: {avg_duration:.0f} minutes " f"({avg_duration/60:.1f} hours)")
        print(f"  Shortest Trade:    {trades_df['duration_minutes'].min():.0f} minutes")
        print(f"  Longest Trade:     {trades_df['duration_minutes'].max():.0f} minutes")

        # Entry time distribution
        trades_df = trades_df.copy()
        trades_df["entry_hour"] = pd.to_datetime(trades_df["entry_time"]).dt.hour
        if not trades_df["entry_hour"].mode().empty:
            print(f"  Most Common Entry Hour: {trades_df['entry_hour'].mode().values[0]}:00 ET")

        # 2. Exit Reason Breakdown
        print("\n🚪 EXIT REASON BREAKDOWN")
        exit_counts = trades_df["exit_reason"].value_counts()
        for reason, count in exit_counts.items():
            pct = (count / len(trades_df)) * 100
            print(f"  {reason}: {count} trades ({pct:.1f}%)")

        # 3. Win/Loss Streaks
        print("\n📊 WIN/LOSS PATTERNS")
        wins = (trades_df["pnl"] > 0).astype(int)
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
        print("\n⚖️  RISK/REWARD ANALYSIS")
        wins_df = trades_df[trades_df["pnl"] > 0]
        losses_df = trades_df[trades_df["pnl"] < 0]

        if not wins_df.empty and not losses_df.empty:
            avg_win = wins_df["pnl"].mean()
            avg_loss = losses_df["pnl"].mean()
            rr_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0
            print(f"  Average Win:  ${avg_win:,.2f}")
            print(f"  Average Loss: ${avg_loss:,.2f}")
            print(f"  Win/Loss Ratio: {rr_ratio:.2f}:1")

            # Expectancy
            win_rate = len(wins_df) / len(trades_df)
            expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)
            print(f"  Expectancy per Trade: ${expectancy:,.2f}")

        # 5. Drawdown Analysis
        print("\n📉 DRAWDOWN ANALYSIS")
        if not equity_curve.empty:
            equity_df = equity_curve.copy()
            equity_df["cummax"] = equity_df["portfolio_value"].cummax()
            equity_df["drawdown"] = equity_df["portfolio_value"] - equity_df["cummax"]
            equity_df["drawdown_pct"] = (equity_df["drawdown"] / equity_df["cummax"]) * 100

            max_dd = equity_df["drawdown"].min()
            max_dd_pct = equity_df["drawdown_pct"].min()
            max_dd_date = equity_df.loc[equity_df["drawdown"].idxmin(), "timestamp"]

            print(f"  Max Drawdown: ${max_dd:,.2f} ({max_dd_pct:.2f}%)")
            print(f"  Max Drawdown Date: {max_dd_date.strftime('%Y-%m-%d %H:%M:%S')}")

        # 6. Profit Distribution
        print("\n💵 PROFIT DISTRIBUTION")
        pnl_std = trades_df["pnl"].std()
        print(f"  Median P&L:    ${trades_df['pnl'].median():,.2f}")
        print(f"  Std Dev:       ${pnl_std:,.2f}")
        print(f"  Best Trade:    ${trades_df['pnl'].max():,.2f}")
        print(f"  Worst Trade:   ${trades_df['pnl'].min():,.2f}")

        # Quartiles
        q1 = trades_df["pnl"].quantile(0.25)
        q3 = trades_df["pnl"].quantile(0.75)
        print(f"  25th Percentile: ${q1:,.2f}")
        print(f"  75th Percentile: ${q3:,.2f}")

        # 7. Entry Trigger Analysis
        print("\n🎯 ENTRY TRIGGER ANALYSIS")
        if "entry_trigger" in trades_df.columns:
            # Group by entry trigger and calculate win rate
            trigger_groups = trades_df.groupby("entry_trigger").agg(
                {"pnl": ["count", "mean", lambda x: (x > 0).sum()]}
            )
            trigger_groups.columns = ["count", "avg_pnl", "wins"]
            trigger_groups["win_rate"] = (trigger_groups["wins"] / trigger_groups["count"]) * 100

            for trigger, stats in trigger_groups.iterrows():
                print(f"  {trigger}:")
                print(
                    f"    Trades: {int(stats['count'])}, "
                    f"Win Rate: {stats['win_rate']:.1f}%, "
                    f"Avg P&L: ${stats['avg_pnl']:,.2f}"
                )

        # 8. Day of Week Performance (if enough data)
        if len(trades_df) >= 5:
            print("\n📆 DAY OF WEEK PERFORMANCE")
            trades_df["day_of_week"] = pd.to_datetime(trades_df["entry_time"]).dt.day_name()
            day_performance = trades_df.groupby("day_of_week").agg(
                {"pnl": ["count", "mean", "sum", lambda x: (x > 0).sum()]}
            )
            day_performance.columns = ["trades", "avg_pnl", "total_pnl", "wins"]
            day_performance["win_rate"] = (
                day_performance["wins"] / day_performance["trades"]
            ) * 100

            # Order by day of week
            day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
            day_performance = day_performance.reindex(
                [d for d in day_order if d in day_performance.index]
            )

            for day, stats in day_performance.iterrows():
                print(
                    f"  {day:9s}: {int(stats['trades'])} trades, "
                    f"{stats['win_rate']:.1f}% win rate, ${stats['avg_pnl']:+,.2f} avg"
                )

        # 9. Return on Capital
        print("\n💰 RETURN METRICS")
        total_capital_deployed = trades_df["entry_cost"].abs().sum()
        total_pnl = trades_df["pnl"].sum()
        if total_capital_deployed > 0:
            roi = (total_pnl / total_capital_deployed) * 100
            print(f"  Total Capital Deployed: ${total_capital_deployed:,.2f}")
            print(f"  Total P&L: ${total_pnl:+,.2f}")
            print(f"  ROI on Deployed Capital: {roi:+.2f}%")

        # Annualized return (if we have date range)
        if len(trades_df) > 0:
            first_trade = pd.to_datetime(trades_df["entry_time"].min())
            last_trade = pd.to_datetime(trades_df["exit_time"].max())
            days_traded = (last_trade - first_trade).days
            if days_traded > 0:
                final_value = initial_capital + total_pnl
                total_return = (final_value / initial_capital - 1) * 100
                annualized_return = (
                    (final_value / initial_capital) ** (365 / days_traded) - 1
                ) * 100
                print(f"  Total Return: {total_return:+.2f}%")
                print(
                    f"  Annualized Return: {annualized_return:+.2f}% "
                    f"(based on {days_traded} days)"
                )
