"""Daily performance reporting for live trading.

Generates comprehensive daily reports tracking progress toward income goals,
win rates, drawdowns, and strategy-level performance.
"""

import json

from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any
import pandas as pd

from quant_vibe.logging import get_logger
from quant_vibe.utils.timestamp_utils import now_utc
from quant_vibe.utils.pnl_utils import PnLCalculator


class DailyPerformanceReport:
    """Generate and manage daily performance reports.

    Tracks actual P&L vs target, win rates, drawdowns, and strategy-level metrics.
    Designed for systematic income generation tracking ($1,780/day target).

        """

    def __init__(
        self,
        target_daily_income: float = 1780.0,
        initial_capital: float = 800000.0,
        max_daily_drawdown_pct: float = 0.02,
    ):
        """Initialize daily performance reporter.

        Args:
            target_daily_income: Daily income goal in dollars (default: $1,780)
            initial_capital: Starting capital (default: $800,000)
            max_daily_drawdown_pct: Maximum acceptable daily drawdown (default: 2%)
        """
        self.target = target_daily_income
        self.initial_capital = initial_capital
        self.max_drawdown_pct = max_daily_drawdown_pct
        self.logger = get_logger(__name__)

    def generate_report(
        self,
        trades_df: pd.DataFrame,
        report_date: datetime,
        equity_curve: Optional[pd.DataFrame] = None
    ) -> Dict[str, Any]:
        """Generate comprehensive daily performance report.

        Args:
            trades_df: DataFrame with trade records (must have columns:
                - entry_time: datetime
                - exit_time: datetime
                - pnl: float
                - strategy: str
                - exit_reason: str (optional)
            report_date: Date for report
            equity_curve: Optional equity curve DataFrame with 'value' column

        Returns:
            dict with report metrics:
                - date: Report date
                - actual_pnl: Total P&L for the day
                - target_pnl: Target income
                - achievement_pct: (actual/target) * 100
                - win_rate: Percentage of winning trades
                - total_trades: Number of trades
                - winning_trades: Number of winners
                - losing_trades: Number of losers
                - avg_win: Average win amount
                - avg_loss: Average loss amount
                - largest_win: Largest single win
                - largest_loss: Largest single loss
                - max_drawdown: Maximum intraday drawdown
                - max_drawdown_pct: Max drawdown as % of starting capital
                - by_strategy: Dict of strategy-level metrics
                - exit_reasons: Breakdown of exit reasons
                - risk_metrics: Risk assessment
        """
        report_date_str = report_date.strftime('%Y-%m-%d')

        # Filter trades for the report date
        if not trades_df.empty:
            # Convert to datetime if needed
            if not pd.api.types.is_datetime64_any_dtype(trades_df['exit_time']):
                trades_df['exit_time'] = pd.to_datetime(trades_df['exit_time'])

            day_trades = trades_df[
                trades_df['exit_time'].dt.date == report_date.date()
            ].copy()
        else:
            day_trades = pd.DataFrame()

        # Calculate basic metrics using centralized PnL aggregation
        if not day_trades.empty:
            # Use centralized PnL aggregator
            pnl_stats = PnLCalculator.aggregate_pnl(day_trades.to_dict('records'))

            total_trades = pnl_stats['total_trades']
            actual_pnl = pnl_stats['total_pnl']
            winning_trades = pnl_stats['num_winners']
            losing_trades = pnl_stats['num_losers']
            win_rate = pnl_stats['win_rate']
            avg_win = pnl_stats['avg_win']
            avg_loss = pnl_stats['avg_loss']
            largest_win = pnl_stats['largest_win']
            largest_loss = pnl_stats['largest_loss']
            profit_factor = pnl_stats['profit_factor']
        else:
            total_trades = 0
            actual_pnl = 0.0
            winning_trades = losing_trades = 0
            win_rate = avg_win = avg_loss = largest_win = largest_loss = 0.0
            profit_factor = 0.0

        # Achievement percentage
        achievement_pct = float((actual_pnl / self.target) * 100) if self.target > 0 else 0.0

        # Strategy-level breakdown
        by_strategy = self._calculate_strategy_metrics(day_trades)

        # Exit reasons breakdown
        exit_reasons = self._calculate_exit_reasons(day_trades)

        # Drawdown analysis
        max_drawdown, max_drawdown_pct = self._calculate_max_drawdown(
            day_trades,
            equity_curve,
            report_date
        )

        # Risk assessment
        risk_metrics = self._assess_risk(
            actual_pnl,
            max_drawdown_pct,
            win_rate,
            total_trades
        )

        # Compile report
        report = {
            'date': report_date_str,
            'actual_pnl': round(actual_pnl, 2),
            'target_pnl': round(self.target, 2),
            'achievement_pct': round(achievement_pct, 1),
            'win_rate': round(win_rate, 1),
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'avg_win': round(avg_win, 2),
            'avg_loss': round(avg_loss, 2),
            'largest_win': round(largest_win, 2),
            'largest_loss': round(largest_loss, 2),
            'profit_factor': profit_factor,  # Now always a valid numeric value
            'max_drawdown': round(max_drawdown, 2),
            'max_drawdown_pct': round(max_drawdown_pct, 2),
            'by_strategy': by_strategy,
            'exit_reasons': exit_reasons,
            'risk_metrics': risk_metrics,
            'generated_at': now_utc().isoformat()
        }

        return report

    def _calculate_strategy_metrics(self, trades_df: pd.DataFrame) -> Dict[str, Dict]:
        """Calculate metrics for each strategy.

        Args:
            trades_df: DataFrame of trades

        Returns:
            Dict mapping strategy name to metrics dict
        """
        if trades_df.empty or 'strategy' not in trades_df.columns:
            return {}

        by_strategy = {}

        for strategy_name in trades_df['strategy'].unique():
            strategy_trades = trades_df[trades_df['strategy'] == strategy_name]

            total = len(strategy_trades)
            pnl = float(strategy_trades['pnl'].sum())
            winners = len(strategy_trades[strategy_trades['pnl'] > 0])
            losers = len(strategy_trades[strategy_trades['pnl'] < 0])
            win_rate = (winners / total) * 100 if total > 0 else 0.0

            by_strategy[str(strategy_name)] = {
                'trades': int(total),
                'pnl': round(pnl, 2),
                'win_rate': round(float(win_rate), 1),
                'winners': int(winners),
                'losers': int(losers)
            }

        return by_strategy

    def _calculate_exit_reasons(self, trades_df: pd.DataFrame) -> Dict[str, int]:
        """Calculate breakdown of exit reasons.

        Args:
            trades_df: DataFrame of trades

        Returns:
            Dict mapping exit reason to count
        """
        if trades_df.empty or 'exit_reason' not in trades_df.columns:
            return {}

        # Convert to native Python types for JSON serialization
        return {str(k): int(v) for k, v in trades_df['exit_reason'].value_counts().to_dict().items()}

    def _calculate_max_drawdown(
        self,
        trades_df: pd.DataFrame,
        equity_curve: Optional[pd.DataFrame],
        report_date: datetime
    ) -> tuple:
        """Calculate maximum intraday drawdown.

        Args:
            trades_df: DataFrame of trades
            equity_curve: Optional equity curve
            report_date: Report date

        Returns:
            Tuple of (max_drawdown_dollars, max_drawdown_pct)
        """
        if equity_curve is None or equity_curve.empty:
            # Estimate from trades if equity curve not available
            if trades_df.empty:
                return 0.0, 0.0

            # Calculate cumulative P&L throughout day
            trades_sorted = trades_df.sort_values('exit_time')
            trades_sorted['cumulative_pnl'] = trades_sorted['pnl'].cumsum()

            # Use centralized max drawdown calculator
            if not trades_sorted.empty:
                dd_value, dd_pct = PnLCalculator.calculate_max_drawdown(
                    trades_sorted['cumulative_pnl']
                )
                max_drawdown = abs(dd_value)
            else:
                max_drawdown = 0.0

        else:
            # Use equity curve if available
            day_equity = equity_curve[
                equity_curve.index.date == report_date.date()
            ]

            if day_equity.empty:
                return 0.0, 0.0

            # Use centralized max drawdown calculator
            dd_value, dd_pct_calc = PnLCalculator.calculate_max_drawdown(
                day_equity['value']
            )
            max_drawdown = abs(dd_value)

        # Calculate percentage
        max_drawdown_pct = (max_drawdown / self.initial_capital) * 100

        return max_drawdown, max_drawdown_pct

    def _assess_risk(
        self,
        actual_pnl: float,
        max_drawdown_pct: float,
        win_rate: float,
        total_trades: int
    ) -> Dict[str, Any]:
        """Assess risk metrics and generate warnings.

        Args:
            actual_pnl: Daily P&L
            max_drawdown_pct: Max drawdown percentage
            win_rate: Win rate percentage
            total_trades: Number of trades

        Returns:
            Dict with risk assessment
        """
        warnings = []
        status = "healthy"

        # Check drawdown limit
        if max_drawdown_pct > self.max_drawdown_pct * 100:
            warnings.append(f"Drawdown {max_drawdown_pct:.1f}% exceeds limit {self.max_drawdown_pct*100:.1f}%")
            status = "critical"
        elif max_drawdown_pct > self.max_drawdown_pct * 50:
            warnings.append(f"Drawdown {max_drawdown_pct:.1f}% approaching limit")
            status = "warning" if status != "critical" else status

        # Check performance vs target
        if actual_pnl < 0:
            warnings.append(f"Negative P&L: ${actual_pnl:.2f}")
            status = "warning" if status == "healthy" else status
        elif actual_pnl < self.target * 0.5:
            warnings.append(f"P&L below 50% of target: ${actual_pnl:.2f} vs ${self.target:.2f}")

        # Check win rate
        if total_trades >= 3 and win_rate < 40:
            warnings.append(f"Low win rate: {win_rate:.1f}%")
            status = "warning" if status == "healthy" else status

        # Check trade count
        if total_trades == 0:
            warnings.append("No trades executed")

        return {
            'status': str(status),
            'warnings': [str(w) for w in warnings],
            'drawdown_ok': bool(max_drawdown_pct <= self.max_drawdown_pct * 100),
            'target_met': bool(actual_pnl >= self.target)
        }

    def save_report(
        self,
        report: Dict[str, Any],
        output_dir: Path,
        save_json: bool = True,
        save_csv: bool = True
    ) -> Dict[str, Path]:
        """Save report to disk.

        Args:
            report: Report dictionary
            output_dir: Output directory
            save_json: Save as JSON
            save_csv: Save as CSV

        Returns:
            Dict mapping format to file path
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        date_str = report['date']
        saved_files = {}

        # Save JSON
        if save_json:
            json_path = output_dir / f"{date_str}_daily_report.json"
            with open(json_path, 'w') as f:
                json.dump(report, f, indent=2)
            saved_files['json'] = json_path
            self.logger.info(f"Saved JSON report: {json_path}")

        # Save CSV (flattened)
        if save_csv:
            csv_path = output_dir / f"{date_str}_daily_report.csv"

            # Flatten report for CSV
            flat_report = {
                'date': report['date'],
                'actual_pnl': report['actual_pnl'],
                'target_pnl': report['target_pnl'],
                'achievement_pct': report['achievement_pct'],
                'win_rate': report['win_rate'],
                'total_trades': report['total_trades'],
                'winning_trades': report['winning_trades'],
                'losing_trades': report['losing_trades'],
                'avg_win': report['avg_win'],
                'avg_loss': report['avg_loss'],
                'profit_factor': report['profit_factor'],
                'max_drawdown': report['max_drawdown'],
                'max_drawdown_pct': report['max_drawdown_pct'],
                'risk_status': report['risk_metrics']['status'],
            }

            df = pd.DataFrame([flat_report])
            df.to_csv(csv_path, index=False)
            saved_files['csv'] = csv_path
            self.logger.info(f"Saved CSV report: {csv_path}")

        return saved_files

    def send_summary(
        self,
        report: Dict[str, Any],
        notifier: Optional[Any] = None
    ) -> bool:
        """Send daily summary via Pushover.

        Args:
            report: Report dictionary
            notifier: TradingNotifier instance (optional)

        Returns:
            True if sent successfully
        """
        if notifier is None or not notifier.notify_daily_summary:
            self.logger.debug("Daily summary notifications disabled")
            return False

        # Format message
        status_emoji = {
            'healthy': '✅',
            'warning': '⚠️',
            'critical': '🚨'
        }

        emoji = status_emoji.get(report['risk_metrics']['status'], '📊')

        message = f"Date: {report['date']}\n"
        message += f"P&L: ${report['actual_pnl']:+,.2f} / ${report['target_pnl']:,.2f}\n"
        message += f"Achievement: {report['achievement_pct']:.1f}%\n"
        message += f"Trades: {report['total_trades']} ({report['win_rate']:.1f}% win rate)\n"
        message += f"Max Drawdown: {report['max_drawdown_pct']:.2f}%"

        # Add warnings if any
        if report['risk_metrics']['warnings']:
            message += "\n\nWarnings:\n" + "\n".join(f"  • {w}" for w in report['risk_metrics']['warnings'])

        # Send via notifier
        try:
            return notifier.send_custom(
                title=f"{emoji} Daily Summary",
                message=message
            )
        except Exception as e:
            self.logger.error(f"Failed to send daily summary: {e}")
            return False

    def get_weekly_summary(
        self,
        reports_dir: Path,
        week_ending: datetime
    ) -> Dict[str, Any]:
        """Generate weekly summary from daily reports.

        Args:
            reports_dir: Directory containing daily reports
            week_ending: End date of week

        Returns:
            Dict with weekly summary metrics
        """
        # Load last 7 days of reports
        reports = []
        for i in range(7):
            day = week_ending.date() - pd.Timedelta(days=i)
            json_file = reports_dir / f"{day.strftime('%Y-%m-%d')}_daily_report.json"

            if json_file.exists():
                with open(json_file, 'r') as f:
                    reports.append(json.load(f))

        if not reports:
            return {'error': 'No reports found for week'}

        # Calculate weekly metrics
        total_pnl = sum(r['actual_pnl'] for r in reports)
        total_target = sum(r['target_pnl'] for r in reports)
        total_trades = sum(r['total_trades'] for r in reports)
        avg_win_rate = sum(r['win_rate'] for r in reports) / len(reports)
        max_daily_drawdown = max(r['max_drawdown_pct'] for r in reports)

        days_met_target = sum(1 for r in reports if r['actual_pnl'] >= r['target_pnl'])

        return {
            'week_ending': week_ending.strftime('%Y-%m-%d'),
            'trading_days': len(reports),
            'total_pnl': round(total_pnl, 2),
            'total_target': round(total_target, 2),
            'achievement_pct': round((total_pnl / total_target) * 100, 1),
            'total_trades': total_trades,
            'avg_win_rate': round(avg_win_rate, 1),
            'days_met_target': days_met_target,
            'max_daily_drawdown': round(max_daily_drawdown, 2)
        }
