"""Backtest results reporting and analytics."""

import pandas as pd


class BacktestReporter:
    """Generate detailed reports and analytics for backtest results."""

    def print_trade_details(self, trades_df: pd.DataFrame) -> None:
        """Print detailed trade-by-trade analysis."""
        print("\n" + "=" * 70)
        print("DETAILED TRADE LOG")
        print("=" * 70)

        if trades_df.empty:
            self._print_no_trades_message()
            return

        for i, trade in trades_df.iterrows():
            self._print_single_trade(i, trade)

    def _print_no_trades_message(self) -> None:
        """Print message when no trades were executed."""
        print("\nNo trades executed during backtest period.")
        print("\nPossible reasons:")
        print("  - Entry conditions not met")
        print("  - Insufficient data for the selected date range")
        print("  - Strategy parameters too restrictive")

    def _print_single_trade(self, index: int, trade: pd.Series) -> None:
        """Print details for a single trade."""
        # Determine win/loss status
        pnl_status = self._get_pnl_status(trade["pnl"])

        print(f"\n{'=' * 70}")
        print(f"TRADE #{index + 1} - {pnl_status}")
        print(f"{'=' * 70}")

        self._print_entry_info(trade)
        self._print_position_info(trade)
        self._print_exit_info(trade)
        self._print_performance_info(trade)

    def _get_pnl_status(self, pnl: float) -> str:
        """Get P&L status string."""
        if pnl > 0:
            return "WIN"
        elif pnl < 0:
            return "LOSS"
        return "BREAK-EVEN"

    def _print_entry_info(self, trade: pd.Series) -> None:
        """Print entry information."""
        print("\nENTRY")
        print(f"  Time:     {trade['entry_time'].strftime('%Y-%m-%d %H:%M:%S ET')}")
        print(f"  Trigger:  {trade.get('entry_trigger', 'N/A')}")
        print(f"  SPX @ Entry: ${trade['entry_underlying_price']:.2f}")

    def _print_position_info(self, trade: pd.Series) -> None:
        """Print position details."""
        print("\nPOSITION")
        print(f"  Type:     {trade['spread_type']}")

        if "legs" in trade and trade["legs"]:
            self._print_leg_details(trade["legs"])

    def _print_leg_details(self, legs: list) -> None:
        """Print details for each leg of the position."""
        print("  Contracts:")
        total_premium_received = 0
        total_premium_paid = 0

        for idx, leg in enumerate(legs, 1):
            action = "SELL" if leg["action"] == "SELL" else "BUY"
            qty = leg["quantity"]
            strike = leg["strike_price"]
            entry_price = leg["entry_price"]
            option_type = leg["option_type"]
            premium_total = entry_price * qty * 100

            if action == "SELL":
                total_premium_received += premium_total
            else:
                total_premium_paid += premium_total

            print(f"    Leg {idx}: {action} {qty} {option_type} @ ${strike:.2f}")
            print(f"            Entry: ${entry_price:.2f} x {qty} x 100 = ${premium_total:,.2f}")

            exit_price = leg.get("exit_price", 0)
            if exit_price > 0:
                exit_total = exit_price * qty * 100
                print(f"            Exit:  ${exit_price:.2f} x {qty} x 100 = ${exit_total:,.2f}")

        # Net Credit/Debit
        net_credit_debit = total_premium_received - total_premium_paid
        if net_credit_debit > 0:
            print(f"\n  Net Credit:  ${net_credit_debit:,.2f} (received)")
        elif net_credit_debit < 0:
            print(f"\n  Net Debit:   ${abs(net_credit_debit):,.2f} (paid)")
        else:
            print("\n  Net:         $0.00 (even)")

    def _print_exit_info(self, trade: pd.Series) -> None:
        """Print exit information."""
        print("\nEXIT")
        print(f"  Time:     {trade['exit_time'].strftime('%Y-%m-%d %H:%M:%S ET')}")
        duration_minutes = trade['duration_minutes']
        print(f"  Duration: {duration_minutes:.0f} minutes ({duration_minutes/60:.1f} hours)")
        print(f"  Reason:   {trade['exit_reason']}")

        if trade.get("exit_underlying_price"):
            exit_price = trade["exit_underlying_price"]
            entry_price = trade["entry_underlying_price"]
            spx_move = exit_price - entry_price
            spx_move_pct = (spx_move / entry_price) * 100
            print(f"  SPX @ Exit:  ${exit_price:.2f}")
            print(f"  SPX Move:    ${spx_move:+.2f} ({spx_move_pct:+.2f}%)")

    def _print_performance_info(self, trade: pd.Series) -> None:
        """Print performance information."""
        print("\nPERFORMANCE")
        print(f"  Entry Premium: ${trade['entry_premium']:,.2f}")
        print(f"  Exit Premium:  ${trade['exit_premium']:,.2f}")
        print(f"  Profit/Loss:   ${trade['pnl']:+,.2f} ({trade['pnl_pct']:+.2f}%)")

        if trade.get("peak_value"):
            peak_pnl = trade["peak_value"] - trade["entry_premium"]
            if trade["entry_premium"] != 0:
                peak_pnl_pct = (peak_pnl / abs(trade["entry_premium"])) * 100
                print(f"  Peak P&L:     ${peak_pnl:+,.2f} ({peak_pnl_pct:+.2f}%)")

                if peak_pnl > trade["pnl"]:
                    profit_given_back = peak_pnl - trade["pnl"]
                    print(f"  Profit Given Back: ${profit_given_back:,.2f}")

    def print_educational_metrics(
        self,
        trades_df: pd.DataFrame,
        equity_curve: pd.DataFrame,
        initial_capital: float,
    ) -> None:
        """Print comprehensive educational metrics and analysis."""
        if trades_df.empty:
            print("\nNo trades executed - no educational metrics to display.")
            return

        print(f"\n{'=' * 70}")
        print("EDUCATIONAL METRICS & ANALYSIS")
        print(f"{'=' * 70}")

        self._print_timing_analysis(trades_df)
        self._print_exit_breakdown(trades_df)
        self._print_win_loss_patterns(trades_df)
        self._print_risk_reward_analysis(trades_df)
        self._print_drawdown_analysis(equity_curve)
        self._print_profit_distribution(trades_df)
        self._print_entry_trigger_analysis(trades_df)
        self._print_day_of_week_performance(trades_df)
        self._print_return_metrics(trades_df, initial_capital)

    def _print_timing_analysis(self, trades_df: pd.DataFrame) -> None:
        """Print trade timing analysis."""
        print("\nTRADE TIMING ANALYSIS")
        avg_duration = trades_df["duration_minutes"].mean()
        print(f"  Average Hold Time: {avg_duration:.0f} minutes ({avg_duration/60:.1f} hours)")
        print(f"  Shortest Trade:    {trades_df['duration_minutes'].min():.0f} minutes")
        print(f"  Longest Trade:     {trades_df['duration_minutes'].max():.0f} minutes")

        # Entry time distribution
        trades_df = trades_df.copy()
        trades_df["entry_hour"] = pd.to_datetime(trades_df["entry_time"]).dt.hour
        mode = trades_df["entry_hour"].mode()
        if not mode.empty:
            print(f"  Most Common Entry Hour: {mode.values[0]}:00 ET")

    def _print_exit_breakdown(self, trades_df: pd.DataFrame) -> None:
        """Print exit reason breakdown."""
        print("\nEXIT REASON BREAKDOWN")
        exit_counts = trades_df["exit_reason"].value_counts()
        for reason, count in exit_counts.items():
            pct = (count / len(trades_df)) * 100
            print(f"  {reason}: {count} trades ({pct:.1f}%)")

    def _print_win_loss_patterns(self, trades_df: pd.DataFrame) -> None:
        """Print win/loss streak patterns."""
        print("\nWIN/LOSS PATTERNS")
        wins = (trades_df["pnl"] > 0).astype(int)
        max_win_streak, max_loss_streak = self._calculate_streaks(wins)
        print(f"  Longest Winning Streak:  {max_win_streak} trades")
        print(f"  Longest Losing Streak:   {max_loss_streak} trades")

    def _calculate_streaks(self, wins: pd.Series) -> tuple[int, int]:
        """Calculate maximum winning and losing streaks."""
        max_win_streak = 0
        max_loss_streak = 0
        current_streak = 1
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

        return max_win_streak, max_loss_streak

    def _print_risk_reward_analysis(self, trades_df: pd.DataFrame) -> None:
        """Print risk/reward analysis."""
        print("\nRISK/REWARD ANALYSIS")
        wins_df = trades_df[trades_df["pnl"] > 0]
        losses_df = trades_df[trades_df["pnl"] < 0]

        if not wins_df.empty and not losses_df.empty:
            avg_win = wins_df["pnl"].mean()
            avg_loss = losses_df["pnl"].mean()
            rr_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0
            win_rate = len(wins_df) / len(trades_df)
            expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)

            print(f"  Average Win:  ${avg_win:,.2f}")
            print(f"  Average Loss: ${avg_loss:,.2f}")
            print(f"  Win/Loss Ratio: {rr_ratio:.2f}:1")
            print(f"  Expectancy per Trade: ${expectancy:,.2f}")

    def _print_drawdown_analysis(self, equity_curve: pd.DataFrame) -> None:
        """Print drawdown analysis."""
        if equity_curve.empty:
            return

        print("\nDRAWDOWN ANALYSIS")
        equity_df = equity_curve.copy()
        equity_df["cummax"] = equity_df["portfolio_value"].cummax()
        equity_df["drawdown"] = equity_df["portfolio_value"] - equity_df["cummax"]
        equity_df["drawdown_pct"] = (equity_df["drawdown"] / equity_df["cummax"]) * 100

        max_dd = equity_df["drawdown"].min()
        max_dd_pct = equity_df["drawdown_pct"].min()
        max_dd_date = equity_df.loc[equity_df["drawdown"].idxmin(), "timestamp"]

        print(f"  Max Drawdown: ${max_dd:,.2f} ({max_dd_pct:.2f}%)")
        print(f"  Max Drawdown Date: {max_dd_date.strftime('%Y-%m-%d %H:%M:%S')}")

    def _print_profit_distribution(self, trades_df: pd.DataFrame) -> None:
        """Print profit distribution statistics."""
        print("\nPROFIT DISTRIBUTION")
        pnl_std = trades_df["pnl"].std()
        q1 = trades_df["pnl"].quantile(0.25)
        q3 = trades_df["pnl"].quantile(0.75)

        print(f"  Median P&L:    ${trades_df['pnl'].median():,.2f}")
        print(f"  Std Dev:       ${pnl_std:,.2f}")
        print(f"  Best Trade:    ${trades_df['pnl'].max():,.2f}")
        print(f"  Worst Trade:   ${trades_df['pnl'].min():,.2f}")
        print(f"  25th Percentile: ${q1:,.2f}")
        print(f"  75th Percentile: ${q3:,.2f}")

    def _print_entry_trigger_analysis(self, trades_df: pd.DataFrame) -> None:
        """Print entry trigger analysis."""
        if "entry_trigger" not in trades_df.columns:
            return

        print("\nENTRY TRIGGER ANALYSIS")
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

    def _print_day_of_week_performance(self, trades_df: pd.DataFrame) -> None:
        """Print performance by day of week."""
        if len(trades_df) < 5:
            return

        print("\nDAY OF WEEK PERFORMANCE")
        trades_df = trades_df.copy()
        trades_df["day_of_week"] = pd.to_datetime(trades_df["entry_time"]).dt.day_name()

        day_performance = trades_df.groupby("day_of_week").agg(
            {"pnl": ["count", "mean", "sum", lambda x: (x > 0).sum()]}
        )
        day_performance.columns = ["trades", "avg_pnl", "total_pnl", "wins"]
        day_performance["win_rate"] = (day_performance["wins"] / day_performance["trades"]) * 100

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

    def _print_return_metrics(self, trades_df: pd.DataFrame, initial_capital: float) -> None:
        """Print return metrics."""
        print("\nRETURN METRICS")
        total_capital_deployed = trades_df["entry_premium"].abs().sum()
        total_pnl = trades_df["pnl"].sum()

        if total_capital_deployed > 0:
            roi = (total_pnl / total_capital_deployed) * 100
            print(f"  Total Capital Deployed: ${total_capital_deployed:,.2f}")
            print(f"  Total P&L: ${total_pnl:+,.2f}")
            print(f"  ROI on Deployed Capital: {roi:+.2f}%")

        # Annualized return
        if len(trades_df) > 0:
            first_trade = pd.to_datetime(trades_df["entry_time"].min())
            last_trade = pd.to_datetime(trades_df["exit_time"].max())
            days_traded = (last_trade - first_trade).days

            if days_traded > 0:
                final_value = initial_capital + total_pnl
                total_return = (final_value / initial_capital - 1) * 100
                annualized_return = ((final_value / initial_capital) ** (365 / days_traded) - 1) * 100
                print(f"  Total Return: {total_return:+.2f}%")
                print(f"  Annualized Return: {annualized_return:+.2f}% (based on {days_traded} days)")