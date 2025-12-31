"""Generate SPX price chart with technical indicators (SMA, EMA, Bollinger Bands).

This script:
1. Derives SPX price from ATM options data
2. Calculates SMA, EMA, and Bollinger Bands
3. Generates an interactive chart

Usage:
    python scripts/chart_spx_with_indicators.py

    # Custom date range
    python scripts/chart_spx_with_indicators.py --start-date 2025-12-01 --end-date 2025-12-12
"""

import sys
from pathlib import Path
import argparse
from datetime import datetime, timedelta
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pytz

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.data.timescale_store import TimescaleStore
from quant_vibe.indicators import calculate_sma, calculate_ema, calculate_bollinger_bands


def get_spx_price_from_options(
    ts_store: TimescaleStore,
    start_time: datetime,
    end_time: datetime,
    interval_minutes: int = 5
) -> pd.DataFrame:
    """
    Derive SPX price from options data.

    Uses the underlying price estimation from ATM options.
    """
    print(f"\nFetching SPX price data from {start_time} to {end_time}...")

    # Get underlying price from options
    spx_data = ts_store.get_underlying_price_from_options(
        underlying_ticker='SPX',
        start_time=start_time,
        end_time=end_time,
    )

    if spx_data.empty:
        print("  ✗ No SPX data found")
        return pd.DataFrame()

    print(f"  ✓ Got {len(spx_data)} price points")

    # Data already has timestamp as index, rename Close to underlying_price
    spx_data = spx_data.rename(columns={'Close': 'underlying_price'})

    # Resample to desired interval for smoother charting
    if interval_minutes > 1:
        spx_data = spx_data.resample(f'{interval_minutes}min').agg({
            'underlying_price': 'last'
        }).dropna()

    # Reset index to have timestamp as column
    spx_data = spx_data.reset_index()

    # Convert to Eastern Time
    eastern = pytz.timezone('America/New_York')
    if spx_data['timestamp'].dt.tz is None:
        spx_data['timestamp'] = spx_data['timestamp'].dt.tz_localize('UTC')
    spx_data['timestamp'] = spx_data['timestamp'].dt.tz_convert(eastern)

    # Filter to market hours only (9:30 AM - 4:00 PM ET)
    spx_data['hour'] = spx_data['timestamp'].dt.hour
    spx_data['minute'] = spx_data['timestamp'].dt.minute

    # Keep only 9:30 AM (9:30) to 4:00 PM (16:00)
    market_hours_mask = (
        ((spx_data['hour'] == 9) & (spx_data['minute'] >= 30)) |
        ((spx_data['hour'] >= 10) & (spx_data['hour'] < 16)) |
        ((spx_data['hour'] == 16) & (spx_data['minute'] == 0))
    )
    spx_data = spx_data[market_hours_mask].copy()

    # Drop temporary columns
    spx_data = spx_data.drop(columns=['hour', 'minute'])

    return spx_data


def calculate_indicators(prices: pd.Series, config: dict) -> pd.DataFrame:
    """
    Calculate technical indicators on price series.

    Args:
        prices: Series of prices
        config: Dict with indicator parameters

    Returns:
        DataFrame with all indicators
    """
    df = pd.DataFrame({'price': prices})

    # SMA
    sma_period = config.get('sma_period', 20)
    df['sma'] = calculate_sma(prices, period=sma_period)

    # EMA
    ema_period = config.get('ema_period', 12)
    df['ema'] = calculate_ema(prices, period=ema_period)

    # Bollinger Bands
    bb_period = config.get('bb_period', 20)
    bb_std = config.get('bb_std', 2)
    bb_upper, bb_middle, bb_lower = calculate_bollinger_bands(
        prices,
        period=bb_period,
        num_std=bb_std
    )
    df['bb_upper'] = bb_upper
    df['bb_middle'] = bb_middle
    df['bb_lower'] = bb_lower

    return df


def create_chart(data: pd.DataFrame, config: dict, output_path: str = None):
    """
    Create and display chart with price and indicators.

    Args:
        data: DataFrame with timestamp, price, and indicators
        config: Dict with chart configuration
        output_path: Optional path to save chart
    """
    print(f"\nCreating chart...")

    # Create figure with subplots
    fig, ax = plt.subplots(figsize=(14, 8))

    # Plot price
    ax.plot(data['timestamp'], data['price'],
            label='SPX Price', color='black', linewidth=1.5, zorder=5)

    # Plot SMA
    ax.plot(data['timestamp'], data['sma'],
            label=f"SMA({config.get('sma_period', 20)})",
            color='blue', linewidth=1.2, alpha=0.8)

    # Plot EMA
    ax.plot(data['timestamp'], data['ema'],
            label=f"EMA({config.get('ema_period', 12)})",
            color='red', linewidth=1.2, alpha=0.8)

    # Plot Bollinger Bands
    bb_period = config.get('bb_period', 20)
    bb_std = config.get('bb_std', 2)

    ax.plot(data['timestamp'], data['bb_upper'],
            label=f"BB Upper ({bb_period}, {bb_std}σ)",
            color='green', linewidth=1, linestyle='--', alpha=0.6)
    ax.plot(data['timestamp'], data['bb_middle'],
            label=f"BB Middle",
            color='green', linewidth=1, linestyle='-', alpha=0.6)
    ax.plot(data['timestamp'], data['bb_lower'],
            label=f"BB Lower",
            color='green', linewidth=1, linestyle='--', alpha=0.6)

    # Fill between Bollinger Bands
    ax.fill_between(data['timestamp'], data['bb_lower'], data['bb_upper'],
                     color='green', alpha=0.1)

    # Formatting
    ax.set_xlabel('Time (EST)', fontsize=12)
    ax.set_ylabel('SPX Price ($)', fontsize=12)

    start_date = data['timestamp'].min().strftime('%Y-%m-%d')
    end_date = data['timestamp'].max().strftime('%Y-%m-%d')
    ax.set_title(f'SPX Price with Technical Indicators\n{start_date} to {end_date}',
                 fontsize=14, fontweight='bold')

    # Format x-axis - show date and time
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d\n%H:%M'))
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
    ax.xaxis.set_minor_locator(mdates.HourLocator(interval=1))
    plt.xticks(rotation=0, ha='center')

    # Grid
    ax.grid(True, alpha=0.3, linestyle='--')

    # Legend
    ax.legend(loc='best', fontsize=10, framealpha=0.9)

    # Tight layout
    plt.tight_layout()

    # Save if path provided
    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"  ✓ Chart saved to: {output_path}")

    # Show
    plt.show()
    print(f"  ✓ Chart displayed")


def main():
    """Main entry point."""

    parser = argparse.ArgumentParser(description="Chart SPX with technical indicators")

    parser.add_argument(
        "--start-date",
        type=str,
        default="2025-12-01",
        help="Start date (YYYY-MM-DD, default: 2025-12-01)"
    )

    parser.add_argument(
        "--end-date",
        type=str,
        default="2025-12-12",
        help="End date (YYYY-MM-DD, default: 2025-12-12)"
    )

    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="Resample interval in minutes (default: 5)"
    )

    parser.add_argument(
        "--sma-period",
        type=int,
        default=20,
        help="SMA period (default: 20)"
    )

    parser.add_argument(
        "--ema-period",
        type=int,
        default=12,
        help="EMA period (default: 12)"
    )

    parser.add_argument(
        "--bb-period",
        type=int,
        default=20,
        help="Bollinger Bands period (default: 20)"
    )

    parser.add_argument(
        "--bb-std",
        type=float,
        default=2.0,
        help="Bollinger Bands standard deviations (default: 2.0)"
    )

    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output file path for chart (default: display only)"
    )

    args = parser.parse_args()

    print("="*70)
    print("SPX PRICE WITH TECHNICAL INDICATORS")
    print("="*70)

    # Parse dates
    start_time = datetime.strptime(args.start_date, "%Y-%m-%d")
    end_time = datetime.strptime(args.end_date, "%Y-%m-%d") + timedelta(days=1)

    # Add timezone
    eastern = pytz.timezone('America/New_York')
    start_time = eastern.localize(start_time)
    end_time = eastern.localize(end_time)

    print(f"\nParameters:")
    print(f"  Date range: {args.start_date} to {args.end_date}")
    print(f"  Interval: {args.interval} minutes")
    print(f"  SMA period: {args.sma_period}")
    print(f"  EMA period: {args.ema_period}")
    print(f"  Bollinger Bands: {args.bb_period} period, {args.bb_std}σ")

    # Initialize TimescaleDB
    print("\nConnecting to TimescaleDB...")
    ts_store = TimescaleStore()
    print("  ✓ Connected")

    # Get SPX price data
    spx_data = get_spx_price_from_options(
        ts_store,
        start_time,
        end_time,
        interval_minutes=args.interval
    )

    if spx_data.empty:
        print("\n❌ No data available for the specified date range")
        print("   Try a different date range or run backfill script first")
        return

    # Calculate indicators
    print(f"\nCalculating indicators...")
    config = {
        'sma_period': args.sma_period,
        'ema_period': args.ema_period,
        'bb_period': args.bb_period,
        'bb_std': args.bb_std,
    }

    indicators = calculate_indicators(spx_data['underlying_price'], config)

    # Combine data
    chart_data = pd.concat([
        spx_data.reset_index(drop=True),
        indicators.reset_index(drop=True)
    ], axis=1)

    # Remove rows with NaN (warmup period for indicators)
    chart_data = chart_data.dropna()

    print(f"  ✓ Calculated {len(indicators.columns) - 1} indicators")
    print(f"  Valid data points: {len(chart_data)}")

    # Create chart
    create_chart(chart_data, config, output_path=args.output)

    # Summary stats
    print(f"\n{'='*70}")
    print("SUMMARY STATISTICS")
    print(f"{'='*70}")
    print(f"SPX Price:")
    print(f"  Min:  ${chart_data['price'].min():.2f}")
    print(f"  Max:  ${chart_data['price'].max():.2f}")
    print(f"  Mean: ${chart_data['price'].mean():.2f}")
    print(f"  Std:  ${chart_data['price'].std():.2f}")

    print(f"\nCurrent values (last timestamp):")
    last_row = chart_data.iloc[-1]
    print(f"  Price:     ${last_row['price']:.2f}")
    print(f"  SMA({args.sma_period}):      ${last_row['sma']:.2f}")
    print(f"  EMA({args.ema_period}):      ${last_row['ema']:.2f}")
    print(f"  BB Upper:  ${last_row['bb_upper']:.2f}")
    print(f"  BB Middle: ${last_row['bb_middle']:.2f}")
    print(f"  BB Lower:  ${last_row['bb_lower']:.2f}")

    # Close database
    ts_store.close()
    print(f"\n✅ Complete")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Stopped by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
