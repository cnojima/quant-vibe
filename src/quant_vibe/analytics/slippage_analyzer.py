"""Slippage analysis for comparing backtest fills to actual paper/live trading fills.

This module provides tools to:
1. Track slippage between expected (backtest) and actual fills
2. Measure in both $ and % terms
3. Break down slippage by various factors (time of day, DTE, spread width, volatility)
4. Generate reports for adjusting backtest assumptions
"""

import pandas as pd
from datetime import datetime
from typing import Dict, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv

load_dotenv()


class SlippageAnalyzer:
    """Analyze slippage between expected and actual fills."""

    def __init__(self, db_profile: Optional[str] = None):
        """
        Initialize slippage analyzer.

        Args:
            db_profile: Database profile ('local' or 'remote').
                       If None, auto-detects from USE_REMOTE_TIMESCALE env var.
        """
        # Determine which database to use
        use_remote = os.getenv('USE_REMOTE_TIMESCALE', 'false').lower() == 'true'

        # Allow manual override via db_profile parameter
        if db_profile == 'remote':
            use_remote = True
        elif db_profile == 'local':
            use_remote = False

        # Use remote or local TimescaleDB config from environment
        if use_remote:
            db_config = {
                'host': os.getenv('REMOTE_TIMESCALE_HOST', '192.168.100.197'),
                'port': int(os.getenv('REMOTE_TIMESCALE_PORT', '5432')),
                'database': os.getenv('REMOTE_TIMESCALE_DB', 'options_data'),
                'user': os.getenv('REMOTE_TIMESCALE_USER', 'quantvibe'),
                'password': os.getenv('REMOTE_TIMESCALE_PASSWORD', 'quantvibe_dev')
            }
        else:
            db_config = {
                'host': os.getenv('TIMESCALE_HOST', 'localhost'),
                'port': int(os.getenv('TIMESCALE_PORT', '5432')),
                'database': os.getenv('TIMESCALE_DB', 'options_data'),
                'user': os.getenv('TIMESCALE_USER', 'quantvibe'),
                'password': os.getenv('TIMESCALE_PASSWORD', 'quantvibe_dev')
            }

        self.conn = psycopg2.connect(**db_config)
        self.cursor = self.conn.cursor(cursor_factory=RealDictCursor)

    def load_filled_orders(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        strategy_name: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Load filled orders from live_orders table.

        Args:
            start_date: Start date for query
            end_date: End date for query
            strategy_name: Filter by strategy name

        Returns:
            DataFrame with columns:
            - order_id, position_id, strategy_name
            - submitted_time, filled_time
            - expected_price, filled_price
            - slippage_dollars, slippage_pct
            - metadata (JSONB with legs info)
        """
        query = """
            SELECT
                order_id,
                position_id,
                strategy_name,
                order_type,
                side,
                quantity,
                symbol,
                submitted_time,
                filled_time,
                expected_price,
                filled_price,
                (filled_price - expected_price) AS slippage_dollars,
                CASE
                    WHEN expected_price != 0 THEN
                        ((filled_price - expected_price) / ABS(expected_price)) * 100
                    ELSE 0
                END AS slippage_pct,
                metadata
            FROM live_orders
            WHERE status = 'filled'
        """

        params = []

        if start_date:
            query += " AND filled_time >= %s"
            params.append(start_date)

        if end_date:
            query += " AND filled_time <= %s"
            params.append(end_date)

        if strategy_name:
            query += " AND strategy_name = %s"
            params.append(strategy_name)

        query += " ORDER BY filled_time ASC"

        self.cursor.execute(query, params)
        rows = self.cursor.fetchall()

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)

        # Parse metadata JSON
        df['legs'] = df['metadata'].apply(lambda x: x.get('legs', []) if x else [])

        return df

    def calculate_slippage_by_time_of_day(self, orders_df: pd.DataFrame) -> pd.DataFrame:
        """
        Break down slippage by time of day.

        Args:
            orders_df: DataFrame from load_filled_orders()

        Returns:
            DataFrame with slippage stats by hour
        """
        if orders_df.empty:
            return pd.DataFrame()

        # Convert to datetime and extract hour
        orders_df = orders_df.copy()
        orders_df['hour'] = pd.to_datetime(orders_df['filled_time']).dt.hour

        # Group by hour
        by_hour = orders_df.groupby('hour').agg({
            'order_id': 'count',
            'slippage_dollars': ['mean', 'std', 'min', 'max'],
            'slippage_pct': ['mean', 'std', 'min', 'max']
        }).round(4)

        by_hour.columns = ['_'.join(col).strip() for col in by_hour.columns.values]
        by_hour.rename(columns={'order_id_count': 'num_orders'}, inplace=True)

        return by_hour

    def calculate_slippage_by_dte(self, orders_df: pd.DataFrame) -> pd.DataFrame:
        """
        Break down slippage by DTE (Days to Expiration).

        Args:
            orders_df: DataFrame from load_filled_orders()

        Returns:
            DataFrame with slippage stats by DTE bucket
        """
        if orders_df.empty:
            return pd.DataFrame()

        # Extract DTE from metadata legs
        def get_dte(row):
            if not row['legs']:
                return None

            # Get expiration from first leg
            first_leg = row['legs'][0]
            exp_str = first_leg.get('expiration', '')

            try:
                if '-' in exp_str:
                    exp_date = datetime.strptime(exp_str, '%Y-%m-%d').date()
                else:
                    exp_date = datetime.strptime(exp_str, '%Y%m%d').date()

                fill_date = pd.to_datetime(row['filled_time']).date()
                dte = (exp_date - fill_date).days
                return max(0, dte)
            except:
                return None

        orders_df = orders_df.copy()
        orders_df['dte'] = orders_df.apply(get_dte, axis=1)

        # Remove rows with no DTE
        orders_df = orders_df[orders_df['dte'].notna()]

        if orders_df.empty:
            return pd.DataFrame()

        # Create DTE buckets
        orders_df['dte_bucket'] = pd.cut(
            orders_df['dte'],
            bins=[-1, 0, 1, 2, 7, 14, 30, 60],
            labels=['0 DTE', '1 DTE', '2 DTE', '3-7 DTE', '8-14 DTE', '15-30 DTE', '31-60 DTE']
        )

        # Group by DTE bucket
        by_dte = orders_df.groupby('dte_bucket', observed=True).agg({
            'order_id': 'count',
            'slippage_dollars': ['mean', 'std', 'min', 'max'],
            'slippage_pct': ['mean', 'std', 'min', 'max']
        }).round(4)

        by_dte.columns = ['_'.join(col).strip() for col in by_dte.columns.values]
        by_dte.rename(columns={'order_id_count': 'num_orders'}, inplace=True)

        return by_dte

    def calculate_slippage_by_spread_width(self, orders_df: pd.DataFrame) -> pd.DataFrame:
        """
        Break down slippage by spread width.

        Args:
            orders_df: DataFrame from load_filled_orders()

        Returns:
            DataFrame with slippage stats by spread width bucket
        """
        if orders_df.empty:
            return pd.DataFrame()

        # Extract spread width from metadata legs
        def get_spread_width(row):
            if not row['legs'] or len(row['legs']) < 2:
                return None

            # Get strikes from legs
            strikes = [leg.get('strike', 0) for leg in row['legs']]
            if not strikes:
                return None

            # Calculate width
            width = abs(max(strikes) - min(strikes))
            return width if width > 0 else None

        orders_df = orders_df.copy()
        orders_df['spread_width'] = orders_df.apply(get_spread_width, axis=1)

        # Remove rows with no spread width
        orders_df = orders_df[orders_df['spread_width'].notna()]

        if orders_df.empty:
            return pd.DataFrame()

        # Create spread width buckets
        orders_df['spread_width_bucket'] = pd.cut(
            orders_df['spread_width'],
            bins=[-1, 5, 10, 15, 20, 30, 50, 100],
            labels=['<5', '5-10', '10-15', '15-20', '20-30', '30-50', '50-100']
        )

        # Group by spread width
        by_width = orders_df.groupby('spread_width_bucket', observed=True).agg({
            'order_id': 'count',
            'slippage_dollars': ['mean', 'std', 'min', 'max'],
            'slippage_pct': ['mean', 'std', 'min', 'max']
        }).round(4)

        by_width.columns = ['_'.join(col).strip() for col in by_width.columns.values]
        by_width.rename(columns={'order_id_count': 'num_orders'}, inplace=True)

        return by_width

    def calculate_slippage_by_strategy(self, orders_df: pd.DataFrame) -> pd.DataFrame:
        """
        Break down slippage by strategy.

        Args:
            orders_df: DataFrame from load_filled_orders()

        Returns:
            DataFrame with slippage stats by strategy
        """
        if orders_df.empty:
            return pd.DataFrame()

        by_strategy = orders_df.groupby('strategy_name').agg({
            'order_id': 'count',
            'slippage_dollars': ['mean', 'std', 'min', 'max'],
            'slippage_pct': ['mean', 'std', 'min', 'max']
        }).round(4)

        by_strategy.columns = ['_'.join(col).strip() for col in by_strategy.columns.values]
        by_strategy.rename(columns={'order_id_count': 'num_orders'}, inplace=True)

        return by_strategy

    def generate_summary_report(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        strategy_name: Optional[str] = None
    ) -> Dict:
        """
        Generate comprehensive slippage summary report.

        Args:
            start_date: Start date for analysis
            end_date: End date for analysis
            strategy_name: Filter by strategy name

        Returns:
            Dict with summary statistics and breakdowns
        """
        # Load orders
        orders_df = self.load_filled_orders(start_date, end_date, strategy_name)

        if orders_df.empty:
            return {
                'error': 'No filled orders found for the specified period',
                'num_orders': 0
            }

        # Overall statistics
        overall = {
            'num_orders': len(orders_df),
            'mean_slippage_dollars': float(orders_df['slippage_dollars'].mean()),
            'std_slippage_dollars': float(orders_df['slippage_dollars'].std()),
            'mean_slippage_pct': float(orders_df['slippage_pct'].mean()),
            'std_slippage_pct': float(orders_df['slippage_pct'].std()),
            'min_slippage_dollars': float(orders_df['slippage_dollars'].min()),
            'max_slippage_dollars': float(orders_df['slippage_dollars'].max()),
            'total_slippage_dollars': float(orders_df['slippage_dollars'].sum()),
        }

        # Breakdowns
        by_hour = self.calculate_slippage_by_time_of_day(orders_df)
        by_dte = self.calculate_slippage_by_dte(orders_df)
        by_width = self.calculate_slippage_by_spread_width(orders_df)
        by_strategy = self.calculate_slippage_by_strategy(orders_df)

        return {
            'overall': overall,
            'by_hour': by_hour.to_dict() if not by_hour.empty else {},
            'by_dte': by_dte.to_dict() if not by_dte.empty else {},
            'by_spread_width': by_width.to_dict() if not by_width.empty else {},
            'by_strategy': by_strategy.to_dict() if not by_strategy.empty else {},
            'date_range': {
                'start': start_date.isoformat() if start_date else None,
                'end': end_date.isoformat() if end_date else None
            }
        }

    def print_summary_report(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        strategy_name: Optional[str] = None
    ):
        """
        Print formatted slippage summary report.

        Args:
            start_date: Start date for analysis
            end_date: End date for analysis
            strategy_name: Filter by strategy name
        """
        report = self.generate_summary_report(start_date, end_date, strategy_name)

        if 'error' in report:
            print(f"\n❌ {report['error']}")
            return

        print("\n" + "="*70)
        print("SLIPPAGE ANALYSIS REPORT")
        print("="*70)

        # Date range
        if report['date_range']['start'] or report['date_range']['end']:
            print(f"\nDate Range: {report['date_range']['start']} to {report['date_range']['end']}")

        if strategy_name:
            print(f"Strategy: {strategy_name}")

        # Overall statistics
        print("\n" + "-"*70)
        print("OVERALL STATISTICS")
        print("-"*70)
        overall = report['overall']
        print(f"Total Orders: {overall['num_orders']}")
        print(f"Mean Slippage: ${overall['mean_slippage_dollars']:.2f} ({overall['mean_slippage_pct']:.2f}%)")
        print(f"Std Dev: ${overall['std_slippage_dollars']:.2f} ({overall['std_slippage_pct']:.2f}%)")
        print(f"Min/Max: ${overall['min_slippage_dollars']:.2f} / ${overall['max_slippage_dollars']:.2f}")
        print(f"Total Slippage: ${overall['total_slippage_dollars']:.2f}")

        # By hour
        if report['by_hour']:
            print("\n" + "-"*70)
            print("SLIPPAGE BY TIME OF DAY")
            print("-"*70)
            by_hour_df = pd.DataFrame(report['by_hour'])
            print(by_hour_df.to_string())

        # By DTE
        if report['by_dte']:
            print("\n" + "-"*70)
            print("SLIPPAGE BY DTE (Days to Expiration)")
            print("-"*70)
            by_dte_df = pd.DataFrame(report['by_dte'])
            print(by_dte_df.to_string())

        # By spread width
        if report['by_spread_width']:
            print("\n" + "-"*70)
            print("SLIPPAGE BY SPREAD WIDTH")
            print("-"*70)
            by_width_df = pd.DataFrame(report['by_spread_width'])
            print(by_width_df.to_string())

        # By strategy
        if report['by_strategy']:
            print("\n" + "-"*70)
            print("SLIPPAGE BY STRATEGY")
            print("-"*70)
            by_strategy_df = pd.DataFrame(report['by_strategy'])
            print(by_strategy_df.to_string())

        print("\n" + "="*70)

    def get_recommended_slippage_adjustments(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict:
        """
        Get recommended slippage parameters for backtest engine.

        Args:
            start_date: Start date for analysis
            end_date: End date for analysis

        Returns:
            Dict with recommended slippage adjustments by DTE
        """
        orders_df = self.load_filled_orders(start_date, end_date)

        if orders_df.empty:
            return {'error': 'No data available'}

        by_dte = self.calculate_slippage_by_dte(orders_df)

        if by_dte.empty:
            return {'error': 'Could not calculate DTE breakdowns'}

        # Extract mean slippage percentages
        recommendations = {}
        for dte_bucket in by_dte.index:
            mean_slippage = by_dte.loc[dte_bucket, 'slippage_pct_mean']
            std_slippage = by_dte.loc[dte_bucket, 'slippage_pct_std']
            num_orders = by_dte.loc[dte_bucket, 'num_orders']

            recommendations[dte_bucket] = {
                'mean_slippage_pct': mean_slippage / 100,  # Convert to decimal
                'std_slippage_pct': std_slippage / 100,
                'num_orders': int(num_orders),
                'confidence': 'high' if num_orders >= 10 else 'low'
            }

        return recommendations

    def close(self):
        """Close database connection."""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
