"""
Result processing for optimization runs.

Handles saving, aggregating, and exporting optimization results.
"""

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from quant_vibe.logging import get_logger
from quant_vibe.utils import now_utc


logger = get_logger(__name__)


class OptimizationResultProcessor:
    """Processes and stores optimization results."""

    def __init__(self, results_base_dir: str = "results/optimization"):
        """Initialize result processor.

        Args:
            results_base_dir: Base directory for saving results
        """
        self.results_base_dir = Path(results_base_dir)
        self.results_base_dir.mkdir(parents=True, exist_ok=True)

    def process_backtest_result(
        self,
        params: Dict[str, Any],
        metrics: Dict[str, float],
    ) -> Dict[str, Any]:
        """Process a single backtest result.

        Args:
            params: Parameter values used
            metrics: Performance metrics from backtest

        Returns:
            Processed result dictionary
        """
        # Combine params and metrics
        result = {
            **params,
            **metrics,
            "timestamp": now_utc().isoformat(),
        }

        # Add calculated metrics
        if "total_return" in metrics and "max_drawdown" in metrics:
            # Calculate return to drawdown ratio
            if metrics["max_drawdown"] != 0:
                result["return_to_drawdown"] = abs(
                    metrics["total_return"] / metrics["max_drawdown"]
                )
            else:
                result["return_to_drawdown"] = float("inf") if metrics["total_return"] > 0 else 0

        # Calculate profit factor if wins and losses available
        if "total_wins" in metrics and "total_losses" in metrics:
            if metrics["total_losses"] != 0:
                result["profit_factor"] = abs(metrics["total_wins"] / metrics["total_losses"])
            else:
                result["profit_factor"] = float("inf") if metrics["total_wins"] > 0 else 0

        return result

    def aggregate_results(
        self,
        results: List[Dict[str, Any]],
        sort_by: str = "sharpe_ratio",
        limit: Optional[int] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Aggregate and sort optimization results.

        Args:
            results: List of result dictionaries
            sort_by: Metric to sort by
            limit: Maximum number of results to return

        Returns:
            Tuple of (sorted_results, summary_stats)
        """
        if not results:
            return [], {}

        # Convert to DataFrame for easier manipulation
        df = pd.DataFrame(results)

        # Sort by metric (descending for positive metrics)
        if sort_by in df.columns:
            ascending = sort_by in ["max_drawdown", "max_consecutive_losses"]
            df = df.sort_values(sort_by, ascending=ascending)

        # Apply limit
        if limit:
            df = df.head(limit)

        # Calculate summary statistics
        numeric_cols = df.select_dtypes(include=["float64", "int64"]).columns
        summary_stats = {}

        for col in numeric_cols:
            if col in df.columns:
                summary_stats[col] = {
                    "mean": float(df[col].mean()),
                    "std": float(df[col].std()),
                    "min": float(df[col].min()),
                    "max": float(df[col].max()),
                    "median": float(df[col].median()),
                }

        # Find best parameters
        best_result = df.iloc[0].to_dict() if not df.empty else {}

        summary_stats["best_params"] = {
            k: v for k, v in best_result.items()
            if k not in numeric_cols and not k.startswith("_")
        }

        summary_stats["best_metrics"] = {
            k: v for k, v in best_result.items()
            if k in numeric_cols
        }

        # Convert back to list of dicts
        sorted_results = df.to_dict("records")

        return sorted_results, summary_stats

    async def save_results_to_csv(
        self,
        optimization_id: str,
        results: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Save optimization results to CSV file.

        Args:
            optimization_id: Optimization ID
            results: List of result dictionaries
            metadata: Optional metadata to include

        Returns:
            Path to saved CSV file
        """
        if not results:
            logger.warning(f"[Results] No results to save for {optimization_id}")
            return ""

        # Create filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"optimization_{optimization_id}_{timestamp}.csv"
        filepath = self.results_base_dir / filename

        try:
            # Convert to DataFrame
            df = pd.DataFrame(results)

            # Add metadata as columns if provided
            if metadata:
                for key, value in metadata.items():
                    if key not in df.columns:
                        df[key] = value

            # Save to CSV
            df.to_csv(filepath, index=False)

            logger.info(
                f"[Results] Saved {len(results)} results to {filepath}"
            )

            return str(filepath)

        except Exception as e:
            logger.error(f"[Results] Error saving CSV: {e}")
            return ""

    def load_results_from_csv(self, filepath: str) -> List[Dict[str, Any]]:
        """Load optimization results from CSV file.

        Args:
            filepath: Path to CSV file

        Returns:
            List of result dictionaries
        """
        try:
            df = pd.read_csv(filepath)
            results = df.to_dict("records")
            logger.info(f"[Results] Loaded {len(results)} results from {filepath}")
            return results

        except Exception as e:
            logger.error(f"[Results] Error loading CSV: {e}")
            return []

    def export_to_json(
        self,
        optimization_id: str,
        results: List[Dict[str, Any]],
        summary: Dict[str, Any],
    ) -> str:
        """Export optimization results to JSON format.

        Args:
            optimization_id: Optimization ID
            results: List of result dictionaries
            summary: Summary statistics

        Returns:
            Path to saved JSON file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"optimization_{optimization_id}_{timestamp}.json"
        filepath = self.results_base_dir / filename

        try:
            export_data = {
                "optimization_id": optimization_id,
                "timestamp": now_utc().isoformat(),
                "summary": summary,
                "results": results,
            }

            with open(filepath, "w") as f:
                json.dump(export_data, f, indent=2, default=str)

            logger.info(f"[Results] Exported to JSON: {filepath}")
            return str(filepath)

        except Exception as e:
            logger.error(f"[Results] Error exporting JSON: {e}")
            return ""

    def create_performance_report(
        self,
        results: List[Dict[str, Any]],
        top_n: int = 10,
    ) -> str:
        """Create a text performance report.

        Args:
            results: List of result dictionaries
            top_n: Number of top results to include

        Returns:
            Formatted performance report
        """
        if not results:
            return "No results available"

        # Sort results by different metrics
        by_sharpe = sorted(results, key=lambda x: x.get("sharpe_ratio", 0), reverse=True)
        by_return = sorted(results, key=lambda x: x.get("total_return", 0), reverse=True)
        by_winrate = sorted(results, key=lambda x: x.get("win_rate", 0), reverse=True)

        report_lines = [
            "=" * 80,
            "OPTIMIZATION PERFORMANCE REPORT",
            "=" * 80,
            "",
            f"Total Combinations Tested: {len(results)}",
            "",
        ]

        # Top results by Sharpe Ratio
        report_lines.extend([
            "-" * 40,
            f"Top {top_n} by Sharpe Ratio:",
            "-" * 40,
        ])

        for i, result in enumerate(by_sharpe[:top_n], 1):
            params_str = ", ".join(
                f"{k}={v}" for k, v in result.items()
                if not k.startswith("_") and k not in ["sharpe_ratio", "total_return", "win_rate", "max_drawdown"]
            )
            report_lines.append(
                f"{i}. Sharpe={result.get('sharpe_ratio', 0):.3f}, "
                f"Return={result.get('total_return', 0):.2%}, "
                f"Params: {params_str}"
            )

        # Top results by Total Return
        report_lines.extend([
            "",
            "-" * 40,
            f"Top {top_n} by Total Return:",
            "-" * 40,
        ])

        for i, result in enumerate(by_return[:top_n], 1):
            params_str = ", ".join(
                f"{k}={v}" for k, v in result.items()
                if not k.startswith("_") and k not in ["sharpe_ratio", "total_return", "win_rate", "max_drawdown"]
            )
            report_lines.append(
                f"{i}. Return={result.get('total_return', 0):.2%}, "
                f"Sharpe={result.get('sharpe_ratio', 0):.3f}, "
                f"Params: {params_str}"
            )

        # Statistics summary
        df = pd.DataFrame(results)
        numeric_cols = ["sharpe_ratio", "total_return", "win_rate", "max_drawdown"]

        report_lines.extend([
            "",
            "-" * 40,
            "Performance Statistics:",
            "-" * 40,
        ])

        for col in numeric_cols:
            if col in df.columns:
                report_lines.append(
                    f"{col}:"
                    f"  Mean={df[col].mean():.3f},"
                    f"  Std={df[col].std():.3f},"
                    f"  Min={df[col].min():.3f},"
                    f"  Max={df[col].max():.3f}"
                )

        report_lines.extend(["", "=" * 80])

        return "\n".join(report_lines)

    def identify_robust_parameters(
        self,
        results: List[Dict[str, Any]],
        stability_threshold: float = 0.8,
    ) -> List[str]:
        """Identify parameters that produce consistent good results.

        Args:
            results: List of result dictionaries
            stability_threshold: Threshold for considering parameter stable

        Returns:
            List of robust parameter names
        """
        if len(results) < 10:
            return []

        df = pd.DataFrame(results)

        # Get top 25% of results by Sharpe ratio
        top_quartile = df.nlargest(len(df) // 4, "sharpe_ratio")

        robust_params = []

        # Check each parameter
        param_cols = [col for col in df.columns
                     if col not in ["sharpe_ratio", "total_return", "win_rate",
                                    "max_drawdown", "timestamp"]]

        for param in param_cols:
            # Get unique values in top quartile
            top_values = top_quartile[param].value_counts()

            # Check if a single value dominates
            if len(top_values) > 0:
                most_common_ratio = top_values.iloc[0] / len(top_quartile)
                if most_common_ratio >= stability_threshold:
                    robust_params.append(param)

        return robust_params