"""
Backtest Results Analyzer

Analyzes backtest results to identify patterns in winning and losing trades,
extract insights, and generate recommendations for strategy improvement.
"""

from typing import Dict, List, Optional, Tuple

import pandas as pd

from quant_vibe.data.timescale_store import TimescaleStore
from quant_vibe.logging.unified_logging import setup_normalized_logging
from quant_vibe.models.analysis import (
    AnalysisFindings,
    AnalysisResult,
    DTEPerformance,
    EntryTimingPattern,
    ExitReasonPattern,
    ExitTiming,
    GreeksAnalysis,
    MacroEvent,
    MarketConditions,
    Patterns,
    StrikeSelectionPattern,
    StrategyAdherence,
    TradeInsight,
    TradeInsights,
)
from quant_vibe.utils import now_utc

logger = setup_normalized_logging(
    app_name="backtest_analyzer",
    log_dir="logs/backtests"
)


class TradeAnalyzer:
    """Analyzes individual trades to extract detailed insights."""

    def __init__(self, trades_df: pd.DataFrame, equity_df: pd.DataFrame, strategy_params: Dict):
        """
        Initialize trade analyzer.

        Args:
            trades_df: DataFrame with trade data
            equity_df: DataFrame with equity curve data
            strategy_params: Strategy configuration parameters
        """
        self.trades_df = trades_df
        self.equity_df = equity_df
        self.strategy_params = strategy_params or {}

    def analyze_trade(self, trade_row: pd.Series) -> TradeInsights:
        """
        Perform comprehensive analysis of a single trade.

        Args:
            trade_row: Series containing trade data

        Returns:
            TradeInsights with detailed analysis
        """
        greeks = self._analyze_greeks(trade_row)
        market_conditions = self._analyze_market_conditions(trade_row)
        strategy_adherence = self._check_strategy_adherence(trade_row)
        exit_timing = self._analyze_exit_timing(trade_row)
        macro_events = self._detect_macro_events(trade_row)

        return TradeInsights(
            greeks=greeks,
            market_conditions=market_conditions,
            strategy_adherence=strategy_adherence,
            exit_timing=exit_timing,
            macro_events=macro_events,
        )

    def _analyze_greeks(self, trade_row: pd.Series) -> GreeksAnalysis:
        """
        Analyze how option Greeks contributed to trade P&L.

        This is a simplified implementation. A full implementation would:
        1. Load option pricing data at entry and exit
        2. Calculate Greeks at both points
        3. Attribute P&L changes to each Greek using finite differences
        """
        pnl = trade_row.get("pnl", 0.0)
        legs = trade_row.get("legs", [])

        # Simplified approach: estimate based on underlying movement
        underlying_entry = trade_row.get("underlying_entry", 0.0)
        underlying_exit = trade_row.get("underlying_exit", 0.0)
        underlying_move_pct = (
            ((underlying_exit - underlying_entry) / underlying_entry * 100)
            if underlying_entry > 0
            else 0.0
        )

        # Estimate Greek contributions (simplified)
        # In reality, this would use actual Greeks from options data
        delta_contribution = min(abs(underlying_move_pct) / 10.0, 0.8)  # Cap at 80%
        theta_contribution = 0.15  # Time decay typically ~15%
        vega_contribution = 0.03  # Volatility changes ~3%
        gamma_contribution = 0.02  # Gamma effects ~2%

        # Determine dominant factor
        contributions = {
            "delta": delta_contribution,
            "theta": theta_contribution,
            "vega": vega_contribution,
            "gamma": gamma_contribution,
        }
        dominant_factor = max(contributions, key=contributions.get)

        # Estimate theta decay
        duration_minutes = trade_row.get("duration_minutes", 0)
        duration_days = duration_minutes / (60 * 24)
        entry_cost = abs(trade_row.get("entry_cost", 0.0))
        theta_decay_total = -entry_cost * 0.01 * duration_days  # ~1% per day (simplified)

        return GreeksAnalysis(
            dominant_factor=dominant_factor,
            delta_contribution=delta_contribution,
            theta_contribution=theta_contribution,
            vega_contribution=vega_contribution,
            gamma_contribution=gamma_contribution,
            entry_delta=None,  # Would calculate from actual Greeks
            exit_delta=None,
            theta_decay_total=theta_decay_total,
        )

    def _analyze_market_conditions(self, trade_row: pd.Series) -> MarketConditions:
        """Analyze market conditions during the trade."""
        underlying_entry = trade_row.get("underlying_entry", 0.0)
        underlying_exit = trade_row.get("underlying_exit", 0.0)

        if underlying_entry > 0:
            underlying_move_pct = (underlying_exit - underlying_entry) / underlying_entry * 100
        else:
            underlying_move_pct = 0.0

        # Determine direction
        if abs(underlying_move_pct) < 0.5:
            direction = "flat"
        elif underlying_move_pct > 0:
            direction = "up"
        else:
            direction = "down"

        # Determine market regime (simplified - would use more sophisticated analysis)
        abs_move = abs(underlying_move_pct)
        if abs_move > 2.0:
            market_regime = "volatile_spike"
        elif abs_move > 1.0:
            market_regime = "trending_up" if underlying_move_pct > 0 else "trending_down"
        else:
            market_regime = "choppy"

        return MarketConditions(
            underlying_move_pct=underlying_move_pct,
            underlying_move_direction=direction,
            volatility_change_pct=None,  # Would calculate from IV data
            market_regime=market_regime,
            intraday_range_pct=None,  # Would calculate from intraday bars
        )

    def _check_strategy_adherence(self, trade_row: pd.Series) -> StrategyAdherence:
        """Check if trade followed strategy rules."""
        violations = []
        edge_cases = []
        legs = trade_row.get("legs", [])

        # Check volume constraints
        min_volume = self.strategy_params.get("min_volume", 0)
        if min_volume > 0 and legs:
            for leg in legs:
                leg_volume = leg.get("volume", 0)
                if leg_volume < min_volume * 1.2:  # Within 20% of minimum
                    edge_cases.append(f"Volume near minimum: {leg_volume}")
                if leg_volume < min_volume:
                    violations.append(f"Volume below minimum: {leg_volume} < {min_volume}")

        # Check bid/ask spread
        max_spread = self.strategy_params.get("max_bid_ask_spread_pct", 100)
        if max_spread < 100 and legs:
            for leg in legs:
                bid = leg.get("bid", 0)
                ask = leg.get("ask", 0)
                if bid > 0:
                    spread_pct = ((ask - bid) / bid) * 100
                    if spread_pct > max_spread * 0.8:  # Within 80% of max
                        edge_cases.append(f"Bid/ask spread near max: {spread_pct:.1f}%")
                    if spread_pct > max_spread:
                        violations.append(f"Bid/ask spread too wide: {spread_pct:.1f}%")

        # Calculate entry quality score (0.0 to 1.0)
        violation_penalty = len(violations) * 0.3
        edge_case_penalty = len(edge_cases) * 0.1
        entry_quality_score = max(0.0, 1.0 - violation_penalty - edge_case_penalty)

        return StrategyAdherence(
            within_all_rules=len(violations) == 0,
            rule_violations=violations,
            edge_case_flags=edge_cases,
            entry_quality_score=entry_quality_score,
        )

    def _analyze_exit_timing(self, trade_row: pd.Series) -> ExitTiming:
        """Analyze exit timing and effectiveness."""
        exit_reason = trade_row.get("exit_reason", "unknown")
        duration_minutes = trade_row.get("duration_minutes", 0)
        pnl = trade_row.get("pnl", 0.0)
        peak_value = trade_row.get("peak_value", trade_row.get("exit_value", 0.0))
        exit_value = trade_row.get("exit_value", 0.0)
        entry_cost = abs(trade_row.get("entry_cost", 1.0))

        # Calculate held percentage (assume max duration is 1 trading day = 390 minutes)
        max_duration = 390.0
        held_pct = min(duration_minutes / max_duration, 1.0) if max_duration > 0 else 0.0

        # Calculate profit captured percentage
        if peak_value > entry_cost:
            profit_captured_pct = (exit_value - entry_cost) / (peak_value - entry_cost) * 100
            profit_captured_pct = max(0.0, min(100.0, profit_captured_pct))
        else:
            profit_captured_pct = 100.0 if pnl >= 0 else 0.0

        # Determine if exit was optimal
        was_optimal = (
            profit_captured_pct > 80.0 or exit_reason == "profit_target" or pnl >= 0
        )

        # Check if better exit existed
        could_have_exited_better = profit_captured_pct < 70.0 and peak_value > exit_value

        timing_notes = None
        if could_have_exited_better:
            missed_profit = peak_value - exit_value
            timing_notes = f"Could have captured ${missed_profit:.2f} more profit"

        return ExitTiming(
            exit_reason=exit_reason,
            held_pct_of_max_duration=held_pct,
            was_optimal=was_optimal,
            profit_captured_pct=profit_captured_pct,
            could_have_exited_better=could_have_exited_better,
            timing_notes=timing_notes,
        )

    def _detect_macro_events(self, trade_row: pd.Series) -> List[MacroEvent]:
        """
        Detect if trade coincided with major market events.

        This is a placeholder implementation. A full version would:
        1. Query external API for FOMC dates, CPI releases, etc.
        2. Check for major earnings announcements
        3. Detect unusual market conditions (VIX spikes, etc.)
        """
        events = []

        # Placeholder: detect if trade was on options expiration day
        entry_time = trade_row.get("entry_time")
        if entry_time is not None:
            # Convert pandas Timestamp to Python datetime if needed
            if hasattr(entry_time, 'to_pydatetime'):
                entry_time = entry_time.to_pydatetime()

            # Check if it's a Friday (simplified expiration detection)
            if hasattr(entry_time, 'weekday') and entry_time.weekday() == 4:  # Friday
                events.append(
                    MacroEvent(
                        event_type="options_expiration",
                        event_date=entry_time,
                        description="Weekly options expiration",
                        proximity_to_trade="during",
                        likely_impact="medium",
                    )
                )

        return events


class PatternExtractor:
    """Extracts patterns across all trades."""

    def __init__(self, trades_df: pd.DataFrame):
        """
        Initialize pattern extractor.

        Args:
            trades_df: DataFrame with trade data
        """
        self.trades_df = trades_df

    def extract_patterns(self) -> Patterns:
        """Extract all patterns from trades."""
        entry_timing = self._analyze_entry_timing()
        exit_reasons = self._analyze_exit_reasons()
        dte_performance = self._analyze_dte_performance()
        strike_selection = self._analyze_strike_selection()

        return Patterns(
            entry_timing=entry_timing,
            exit_reasons=exit_reasons,
            dte_performance=dte_performance,
            strike_selection=strike_selection,
        )

    def _analyze_entry_timing(self) -> Optional[EntryTimingPattern]:
        """Analyze entry timing patterns."""
        if "entry_time" not in self.trades_df.columns or self.trades_df.empty:
            return None

        # Extract hour from entry_time
        self.trades_df["entry_hour"] = pd.to_datetime(
            self.trades_df["entry_time"]
        ).dt.hour

        # Calculate stats by hour
        hourly_stats = {}
        for hour in range(24):
            hour_trades = self.trades_df[self.trades_df["entry_hour"] == hour]
            if len(hour_trades) > 0:
                hourly_stats[hour] = {
                    "avg_pnl": float(hour_trades["pnl"].mean()),
                    "win_rate": float((hour_trades["pnl"] > 0).mean()),
                    "count": int(len(hour_trades)),
                }

        if not hourly_stats:
            return None

        # Find best and worst hours
        best_hour = max(hourly_stats.items(), key=lambda x: x[1]["avg_pnl"])[0]
        worst_hour = min(hourly_stats.items(), key=lambda x: x[1]["avg_pnl"])[0]

        return EntryTimingPattern(
            best_hour=best_hour,
            worst_hour=worst_hour,
            hourly_stats=hourly_stats,
        )

    def _analyze_exit_reasons(self) -> Optional[ExitReasonPattern]:
        """Analyze exit reason patterns."""
        if "exit_reason" not in self.trades_df.columns or self.trades_df.empty:
            return None

        exit_reason_groups = self.trades_df.groupby("exit_reason")

        # Calculate win rates by exit reason
        exit_reason_stats = {}
        for reason, group in exit_reason_groups:
            exit_reason_stats[reason] = {
                "win_rate": float((group["pnl"] > 0).mean()),
                "count": int(len(group)),
                "avg_pnl": float(group["pnl"].mean()),
            }

        # Extract specific win rates
        profit_target_wr = exit_reason_stats.get("profit_target", {}).get("win_rate", 0.0)
        stop_loss_wr = exit_reason_stats.get("stop_loss", {}).get("win_rate", 0.0)
        expiration_wr = exit_reason_stats.get("expiration", {}).get("win_rate", 0.0)
        trailing_stop_wr = exit_reason_stats.get("trailing_stop", {}).get("win_rate", 0.0)

        exit_reason_counts = {
            reason: stats["count"] for reason, stats in exit_reason_stats.items()
        }
        exit_reason_avg_pnl = {
            reason: stats["avg_pnl"] for reason, stats in exit_reason_stats.items()
        }

        return ExitReasonPattern(
            profit_target_win_rate=profit_target_wr,
            stop_loss_win_rate=stop_loss_wr,
            expiration_win_rate=expiration_wr,
            trailing_stop_win_rate=trailing_stop_wr,
            exit_reason_counts=exit_reason_counts,
            exit_reason_avg_pnl=exit_reason_avg_pnl,
        )

    def _analyze_dte_performance(self) -> Optional[DTEPerformance]:
        """Analyze performance by days to expiration."""
        # Calculate DTE from legs data (simplified)
        if self.trades_df.empty:
            return None

        # This is a placeholder - would calculate actual DTE from leg data
        dte_buckets = {
            "0_dte": {"avg_pnl": 0.0, "win_rate": 0.0, "count": 0},
            "1-2_dte": {"avg_pnl": 0.0, "win_rate": 0.0, "count": 0},
            "3-7_dte": {"avg_pnl": 0.0, "win_rate": 0.0, "count": 0},
        }

        # Find optimal range (placeholder)
        optimal_dte_range = "1-2_dte"

        return DTEPerformance(
            dte_buckets=dte_buckets,
            optimal_dte_range=optimal_dte_range,
        )

    def _analyze_strike_selection(self) -> Optional[StrikeSelectionPattern]:
        """Analyze strike selection patterns."""
        # This is a placeholder - would calculate OTM % from leg data
        if self.trades_df.empty:
            return None

        otm_pct_buckets = {
            "0-5_pct": {"avg_pnl": 0.0, "win_rate": 0.0, "count": 0},
            "5-10_pct": {"avg_pnl": 0.0, "win_rate": 0.0, "count": 0},
            "10-15_pct": {"avg_pnl": 0.0, "win_rate": 0.0, "count": 0},
        }

        return StrikeSelectionPattern(
            otm_pct_buckets=otm_pct_buckets,
            optimal_otm_pct=7.5,  # Placeholder
        )


class NarrativeGenerator:
    """Generates human-readable markdown summaries."""

    def generate_summary(self, findings: AnalysisFindings, total_trades: int) -> str:
        """Generate markdown summary of analysis findings."""
        lines = ["# Backtest Analysis Summary", ""]

        # Overview
        lines.append(f"**Total Trades Analyzed:** {total_trades}")
        lines.append(f"**Big Winners Identified:** {len(findings.big_winners)}")
        lines.append(f"**Big Losers Identified:** {len(findings.big_losers)}")
        lines.append("")

        # Big Winners Section
        if findings.big_winners:
            lines.append("## Big Winners Analysis")
            lines.append("")
            for i, winner in enumerate(findings.big_winners[:5], 1):  # Top 5
                lines.append(f"### Winner #{i}: ${winner.pnl:,.2f} profit")
                lines.append(f"- **P&L:** ${winner.pnl:,.2f} ({winner.pnl_pct:.1f}%)")
                lines.append(f"- **Outlier Score:** {winner.std_devs_from_mean:.1f} std devs")
                lines.append(f"- **Key Takeaway:** {winner.key_takeaway}")
                lines.append(f"- **Dominant Factor:** {winner.insights.greeks.dominant_factor}")
                lines.append(
                    f"- **Market Move:** {winner.insights.market_conditions.underlying_move_direction} "
                    f"{abs(winner.insights.market_conditions.underlying_move_pct):.1f}%"
                )
                lines.append("")

        # Big Losers Section
        if findings.big_losers:
            lines.append("## Big Losers Analysis")
            lines.append("")
            for i, loser in enumerate(findings.big_losers[:5], 1):  # Top 5
                lines.append(f"### Loser #{i}: ${loser.pnl:,.2f} loss")
                lines.append(f"- **P&L:** ${loser.pnl:,.2f} ({loser.pnl_pct:.1f}%)")
                lines.append(f"- **Outlier Score:** {loser.std_devs_from_mean:.1f} std devs")
                lines.append(f"- **Key Takeaway:** {loser.key_takeaway}")
                if loser.insights.strategy_adherence.rule_violations:
                    lines.append("- **Rule Violations:**")
                    for violation in loser.insights.strategy_adherence.rule_violations:
                        lines.append(f"  - {violation}")
                if loser.insights.exit_timing.could_have_exited_better:
                    lines.append(f"- **Exit Issue:** {loser.insights.exit_timing.timing_notes}")
                lines.append("")

        # Pattern Summary
        patterns = findings.patterns
        if patterns.entry_timing:
            lines.append("## Entry Timing Patterns")
            lines.append(
                f"- **Best Hour:** {patterns.entry_timing.best_hour}:00 "
                f"(Avg P&L: ${patterns.entry_timing.hourly_stats.get(patterns.entry_timing.best_hour, {}).get('avg_pnl', 0):.2f})"
            )
            lines.append(
                f"- **Worst Hour:** {patterns.entry_timing.worst_hour}:00 "
                f"(Avg P&L: ${patterns.entry_timing.hourly_stats.get(patterns.entry_timing.worst_hour, {}).get('avg_pnl', 0):.2f})"
            )
            lines.append("")

        if patterns.exit_reasons:
            lines.append("## Exit Reason Performance")
            lines.append(
                f"- **Profit Target Win Rate:** {patterns.exit_reasons.profit_target_win_rate:.1%}"
            )
            lines.append(
                f"- **Stop Loss Win Rate:** {patterns.exit_reasons.stop_loss_win_rate:.1%}"
            )
            lines.append(
                f"- **Expiration Win Rate:** {patterns.exit_reasons.expiration_win_rate:.1%}"
            )
            lines.append("")

        return "\n".join(lines)

    def generate_recommendations(
        self, findings: AnalysisFindings, total_trades: int
    ) -> str:
        """Generate markdown recommendations based on findings."""
        lines = ["# Strategy Improvement Recommendations", ""]

        recommendations_count = 0

        # Analyze big losers for improvement opportunities
        if findings.big_losers:
            lines.append("## Risk Management Improvements")
            lines.append("")

            # Check for exit timing issues
            exit_issues = sum(
                1
                for loser in findings.big_losers
                if loser.insights.exit_timing.could_have_exited_better
            )
            if exit_issues > len(findings.big_losers) / 2:
                recommendations_count += 1
                lines.append(
                    f"{recommendations_count}. **Improve Exit Timing:** "
                    f"{exit_issues} of {len(findings.big_losers)} big losers had suboptimal exits. "
                    "Consider tightening stop losses or using trailing stops more aggressively."
                )
                lines.append("")

            # Check for rule violations
            violations = [
                loser
                for loser in findings.big_losers
                if loser.insights.strategy_adherence.rule_violations
            ]
            if violations:
                recommendations_count += 1
                lines.append(
                    f"{recommendations_count}. **Enforce Entry Rules:** "
                    f"{len(violations)} big losers violated strategy rules. "
                    "Strengthen entry filters to avoid edge cases."
                )
                lines.append("")

        # Analyze big winners for generalization
        if findings.big_winners:
            lines.append("## Strategy Enhancement Opportunities")
            lines.append("")

            high_potential = [
                w for w in findings.big_winners if w.generalization_potential == "high"
            ]
            if high_potential:
                recommendations_count += 1
                lines.append(
                    f"{recommendations_count}. **Generalize Winning Patterns:** "
                    f"{len(high_potential)} big winners show high generalization potential. "
                    "Consider these patterns:"
                )
                for winner in high_potential[:3]:
                    lines.append(f"   - {winner.key_takeaway}")
                lines.append("")

        # Entry timing recommendations
        if findings.patterns.entry_timing:
            best_hour = findings.patterns.entry_timing.best_hour
            worst_hour = findings.patterns.entry_timing.worst_hour
            best_stats = findings.patterns.entry_timing.hourly_stats.get(best_hour, {})
            worst_stats = findings.patterns.entry_timing.hourly_stats.get(worst_hour, {})

            if best_stats.get("count", 0) > 3 and worst_stats.get("count", 0) > 3:
                best_pnl = best_stats.get("avg_pnl", 0)
                worst_pnl = worst_stats.get("avg_pnl", 0)
                if best_pnl - worst_pnl > 100:  # Significant difference
                    recommendations_count += 1
                    lines.append(
                        f"{recommendations_count}. **Optimize Entry Timing:** "
                        f"Trades at {best_hour}:00 perform significantly better "
                        f"(${best_pnl:.2f} avg) than {worst_hour}:00 (${worst_pnl:.2f} avg). "
                        f"Consider restricting entries to better-performing hours."
                    )
                    lines.append("")

        # Exit reason recommendations
        if findings.patterns.exit_reasons:
            exit_stats = findings.patterns.exit_reasons
            if exit_stats.stop_loss_win_rate < 0.3:  # Less than 30% win rate on stop losses
                recommendations_count += 1
                lines.append(
                    f"{recommendations_count}. **Reassess Stop Loss Levels:** "
                    f"Stop loss exits show only {exit_stats.stop_loss_win_rate:.1%} win rate. "
                    "This may indicate stops are too tight or entries are poorly timed."
                )
                lines.append("")

        if recommendations_count == 0:
            lines.append("No significant improvement opportunities identified at this time.")
            lines.append("")

        return "\n".join(lines)


class BacktestAnalyzer:
    """Main analyzer coordinating all analysis components."""

    def __init__(self, backtest_id: str):
        """
        Initialize backtest analyzer.

        Args:
            backtest_id: Unique identifier for the backtest
        """
        self.backtest_id = backtest_id
        self.ts_store = TimescaleStore()
        self.trades_df: Optional[pd.DataFrame] = None
        self.equity_df: Optional[pd.DataFrame] = None
        self.backtest_run: Optional[Dict] = None

    async def analyze(self, outlier_std_devs: float = 2.0) -> AnalysisResult:
        """
        Run comprehensive backtest analysis.

        Args:
            outlier_std_devs: Standard deviation threshold for outlier detection

        Returns:
            Complete analysis result
        """
        logger.info(f"Starting analysis for backtest {self.backtest_id}")

        # Load data
        await self._load_data()

        if self.trades_df is None or self.trades_df.empty:
            raise ValueError(f"No trades found for backtest {self.backtest_id}")

        # Identify outliers
        big_winners, big_losers = self._identify_outliers(outlier_std_devs)

        # Analyze outlier trades
        strategy_params = self.backtest_run.get("parameters", {}) if self.backtest_run else {}
        trade_analyzer = TradeAnalyzer(self.trades_df, self.equity_df, strategy_params)

        analyzed_winners = []
        for _, trade_row in big_winners.iterrows():
            insights = trade_analyzer.analyze_trade(trade_row)
            key_takeaway = self._generate_trade_takeaway(trade_row, insights, is_winner=True)
            generalization_potential = self._assess_generalization_potential(
                trade_row, insights
            )

            analyzed_winners.append(
                TradeInsight(
                    trade_id=str(trade_row.get("trade_id", "")),
                    pnl=float(trade_row.get("pnl", 0.0)),
                    pnl_pct=float(trade_row.get("pnl_pct", 0.0)),
                    std_devs_from_mean=float(trade_row.get("std_devs_from_mean", 0.0)),
                    insights=insights,
                    generalization_potential=generalization_potential,
                    key_takeaway=key_takeaway,
                )
            )

        analyzed_losers = []
        for _, trade_row in big_losers.iterrows():
            insights = trade_analyzer.analyze_trade(trade_row)
            key_takeaway = self._generate_trade_takeaway(trade_row, insights, is_winner=False)
            generalization_potential = self._assess_generalization_potential(
                trade_row, insights
            )

            analyzed_losers.append(
                TradeInsight(
                    trade_id=str(trade_row.get("trade_id", "")),
                    pnl=float(trade_row.get("pnl", 0.0)),
                    pnl_pct=float(trade_row.get("pnl_pct", 0.0)),
                    std_devs_from_mean=float(trade_row.get("std_devs_from_mean", 0.0)),
                    insights=insights,
                    generalization_potential=generalization_potential,
                    key_takeaway=key_takeaway,
                )
            )

        # Extract patterns
        pattern_extractor = PatternExtractor(self.trades_df)
        patterns = pattern_extractor.extract_patterns()

        # Create findings
        findings = AnalysisFindings(
            big_winners=analyzed_winners,
            big_losers=analyzed_losers,
            patterns=patterns,
        )

        # Generate narratives
        narrative_gen = NarrativeGenerator()
        summary = narrative_gen.generate_summary(findings, len(self.trades_df))
        recommendations = narrative_gen.generate_recommendations(findings, len(self.trades_df))

        # Create result
        result = AnalysisResult(
            backtest_id=self.backtest_id,
            analyzed_at=now_utc(),
            total_trades=len(self.trades_df),
            outlier_threshold_pct=outlier_std_devs,
            num_big_winners=len(analyzed_winners),
            num_big_losers=len(analyzed_losers),
            findings=findings,
            summary_markdown=summary,
            recommendations_markdown=recommendations,
        )

        logger.info(
            f"Analysis complete: {result.num_big_winners} winners, "
            f"{result.num_big_losers} losers identified"
        )

        return result

    async def _load_data(self):
        """Load backtest data from database."""
        self.backtest_run = self.ts_store.get_backtest_run(self.backtest_id)
        self.trades_df = self.ts_store.get_backtest_trades(self.backtest_id)
        self.equity_df = self.ts_store.get_backtest_equity_curve(self.backtest_id)

    def _identify_outliers(
        self, outlier_std_devs: float
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Identify outlier trades using statistical methods.

        Args:
            outlier_std_devs: Number of standard deviations for outlier threshold

        Returns:
            Tuple of (big_winners_df, big_losers_df)
        """
        if self.trades_df is None or self.trades_df.empty:
            return pd.DataFrame(), pd.DataFrame()

        # Calculate statistics
        pnl_mean = self.trades_df["pnl"].mean()
        pnl_std = self.trades_df["pnl"].std()

        # Calculate z-scores
        self.trades_df["std_devs_from_mean"] = (
            (self.trades_df["pnl"] - pnl_mean) / pnl_std
            if pnl_std > 0
            else 0.0
        )

        # Identify outliers
        big_winners = self.trades_df[
            self.trades_df["std_devs_from_mean"] > outlier_std_devs
        ].sort_values("pnl", ascending=False)

        big_losers = self.trades_df[
            self.trades_df["std_devs_from_mean"] < -outlier_std_devs
        ].sort_values("pnl", ascending=True)

        logger.info(
            f"Identified {len(big_winners)} big winners and {len(big_losers)} big losers "
            f"using {outlier_std_devs} std dev threshold"
        )

        return big_winners, big_losers

    def _generate_trade_takeaway(
        self, trade_row: pd.Series, insights: TradeInsights, is_winner: bool
    ) -> str:
        """Generate one-sentence key takeaway for a trade."""
        pnl = trade_row.get("pnl", 0.0)
        dominant_greek = insights.greeks.dominant_factor
        market_move = insights.market_conditions.underlying_move_pct

        if is_winner:
            return (
                f"Profited ${pnl:.2f} primarily from {dominant_greek} exposure "
                f"during {abs(market_move):.1f}% {insights.market_conditions.underlying_move_direction} move"
            )
        else:
            exit_issue = (
                "with poor exit timing"
                if insights.exit_timing.could_have_exited_better
                else f"via {insights.exit_timing.exit_reason}"
            )
            return (
                f"Lost ${abs(pnl):.2f} due to {dominant_greek} exposure "
                f"during {abs(market_move):.1f}% {insights.market_conditions.underlying_move_direction} move, "
                f"exited {exit_issue}"
            )

    def _assess_generalization_potential(
        self, trade_row: pd.Series, insights: TradeInsights
    ) -> str:
        """Assess how likely a trade pattern can be generalized."""
        score = 0

        # High quality entry → more generalizable
        if insights.strategy_adherence.entry_quality_score > 0.8:
            score += 2

        # No rule violations → more generalizable
        if insights.strategy_adherence.within_all_rules:
            score += 1

        # Optimal exit → more generalizable
        if insights.exit_timing.was_optimal:
            score += 1

        # Clear dominant Greek → more generalizable
        if insights.greeks.delta_contribution > 0.7:
            score += 1

        # Map score to category
        if score >= 4:
            return "high"
        elif score >= 2:
            return "medium"
        else:
            return "low"
