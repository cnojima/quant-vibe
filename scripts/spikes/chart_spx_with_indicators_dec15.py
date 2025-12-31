"""Chart SPX price with technical indicators for December 15, 2025.

Creates a chart showing:
- SPX price (derived from ATM options)
- Simple Moving Average (SMA)
- Exponential Moving Average (EMA)
- Bollinger Bands
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.data.timescale_store import TimescaleStore
from quant_vibe.indicators.technical import (
    calculate_sma,
    calculate_ema,
    calculate_bollinger_bands
)


def get_spx_price_from_options(ts_store, start_time, end_time):
    """Derive SPX price from ATM options."""

    query = """
    SELECT
        timestamp,
        strike_price,
        contract_type,
        close,
        delta,
        volume
    FROM options_bars
    WHERE data_source = 'schwab_poll'
        AND timestamp >= %s
        AND timestamp <= %s
        AND delta IS NOT NULL
    ORDER BY timestamp, strike_price
    """

    with ts_store.get_connection() as conn:
        df = pd.read_sql_query(
            query,
            conn,
            params=[start_time, end_time],
            parse_dates=['timestamp']
        )

    if df.empty:
        return pd.DataFrame()

    # Get ATM options to estimate SPX price (use calls with delta near 0.5)
    atm_prices = []

    for ts in df['timestamp'].unique():
        ts_data = df[df['timestamp'] == ts]

        # Find calls closest to ATM (delta near 0.5)
        calls = ts_data[ts_data['contract_type'] == 'call'].copy()

        if not calls.empty:
            calls['delta_diff'] = (calls['delta'] - 0.5).abs()
            atm_call = calls.nsmallest(1, 'delta_diff')

            if not atm_call.empty and atm_call.iloc[0]['delta_diff'] < 0.1:
                atm_prices.append({
                    'timestamp': ts,
                    'Close': atm_call.iloc[0]['strike_price'],  # Use strike as SPX price estimate
                })

    spx_df = pd.DataFrame(atm_prices)

    if not spx_df.empty:
        spx_df.set_index('timestamp', inplace=True)
        spx_df.index = spx_df.index.tz_convert('America/New_York')

    return spx_df


def chart_spx_with_indicators():
    """Create SPX chart with technical indicators."""

    ts_store = TimescaleStore()

    print("="*70)
    print("SPX PRICE WITH TECHNICAL INDICATORS - December 15, 2025")
    print("="*70)

    # December 15, 2025 (UTC)
    target_date = datetime(2025, 12, 15, tzinfo=timezone.utc)
    start_time = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_time = target_date.replace(hour=23, minute=59, second=59)

    print(f"\nFetching data for December 15, 2025...")

    try:
        # Get SPX price from options
        spx_df = get_spx_price_from_options(ts_store, start_time, end_time)

        if spx_df.empty:
            print("\n❌ No data found for December 15, 2025")
            return

        print(f"✅ Found {len(spx_df)} SPX price points")
        print(f"Time range: {spx_df.index.min()} to {spx_df.index.max()}")
        print(f"Price range: ${spx_df['Close'].min():.2f} - ${spx_df['Close'].max():.2f}")

        # Calculate technical indicators
        print("\nCalculating technical indicators...")

        # Use 20-period for indicators (20 minutes since we have 1-min data)
        period = 20

        # SMA
        spx_df['SMA'] = calculate_sma(spx_df['Close'], period=period)

        # EMA
        spx_df['EMA'] = calculate_ema(spx_df['Close'], period=period)

        # Bollinger Bands (returns tuple of upper, middle, lower)
        bb_upper, bb_middle, bb_lower = calculate_bollinger_bands(spx_df['Close'], period=period, num_std=2.0)
        spx_df['BB_Upper'] = bb_upper
        spx_df['BB_Middle'] = bb_middle
        spx_df['BB_Lower'] = bb_lower

        # Create the chart
        fig, ax = plt.subplots(figsize=(16, 10))

        # Plot Bollinger Bands first (as background)
        ax.fill_between(spx_df.index, spx_df['BB_Upper'], spx_df['BB_Lower'],
                        alpha=0.2, color='gray', label='Bollinger Bands (±2σ)')
        ax.plot(spx_df.index, spx_df['BB_Upper'], 'k--', linewidth=1, alpha=0.5)
        ax.plot(spx_df.index, spx_df['BB_Lower'], 'k--', linewidth=1, alpha=0.5)
        ax.plot(spx_df.index, spx_df['BB_Middle'], 'k:', linewidth=1.5, alpha=0.6,
               label=f'BB Middle (SMA {period})')

        # Plot price
        ax.plot(spx_df.index, spx_df['Close'], linewidth=2.5, color='#1f77b4',
               label='SPX Price', zorder=5)

        # Plot SMA
        ax.plot(spx_df.index, spx_df['SMA'], linewidth=2, color='orange',
               label=f'SMA ({period})', linestyle='-', alpha=0.8)

        # Plot EMA
        ax.plot(spx_df.index, spx_df['EMA'], linewidth=2, color='green',
               label=f'EMA ({period})', linestyle='-', alpha=0.8)

        # Formatting
        ax.set_xlabel('Time (Eastern)', fontsize=13, fontweight='bold')
        ax.set_ylabel('Price ($)', fontsize=13, fontweight='bold')
        ax.set_title('SPX Price with Technical Indicators - December 15, 2025',
                    fontsize=16, fontweight='bold', pad=20)

        # Format x-axis
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz='America/New_York'))
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
        plt.xticks(rotation=45, ha='right')

        # Grid
        ax.grid(True, alpha=0.3, linestyle='--')

        # Legend
        ax.legend(loc='upper left', fontsize=11, framealpha=0.9)

        # Add statistics box
        stats_text = f"""Statistics:
Open: ${spx_df['Close'].iloc[0]:.2f}
High: ${spx_df['Close'].max():.2f}
Low: ${spx_df['Close'].min():.2f}
Close: ${spx_df['Close'].iloc[-1]:.2f}
Range: ${spx_df['Close'].max() - spx_df['Close'].min():.2f}

Indicators ({period}-period):
SMA: ${spx_df['SMA'].iloc[-1]:.2f}
EMA: ${spx_df['EMA'].iloc[-1]:.2f}
BB Upper: ${spx_df['BB_Upper'].iloc[-1]:.2f}
BB Lower: ${spx_df['BB_Lower'].iloc[-1]:.2f}"""

        # Add text box
        props = dict(boxstyle='round', facecolor='wheat', alpha=0.8)
        ax.text(0.02, 0.98, stats_text, transform=ax.transAxes,
               fontsize=10, verticalalignment='top', bbox=props,
               family='monospace')

        plt.tight_layout()

        # Save chart
        output_file = Path(__file__).parent.parent / "data" / "spx_indicators_dec15.png"
        output_file.parent.mkdir(exist_ok=True)
        plt.savefig(output_file, dpi=150, bbox_inches='tight')

        print(f"\n✅ Chart saved to: {output_file}")

        # Print summary statistics
        print("\n" + "="*70)
        print("SUMMARY STATISTICS")
        print("="*70)
        print(f"\nPrice Action:")
        print(f"  Open:  ${spx_df['Close'].iloc[0]:.2f}")
        print(f"  High:  ${spx_df['Close'].max():.2f}")
        print(f"  Low:   ${spx_df['Close'].min():.2f}")
        print(f"  Close: ${spx_df['Close'].iloc[-1]:.2f}")
        print(f"  Range: ${spx_df['Close'].max() - spx_df['Close'].min():.2f}")

        print(f"\nIndicators (Final Values):")
        print(f"  SMA-{period}:     ${spx_df['SMA'].iloc[-1]:.2f}")
        print(f"  EMA-{period}:     ${spx_df['EMA'].iloc[-1]:.2f}")
        print(f"  BB Upper:  ${spx_df['BB_Upper'].iloc[-1]:.2f}")
        print(f"  BB Middle: ${spx_df['BB_Middle'].iloc[-1]:.2f}")
        print(f"  BB Lower:  ${spx_df['BB_Lower'].iloc[-1]:.2f}")

        # Price position relative to bands
        current_price = spx_df['Close'].iloc[-1]
        bb_upper = spx_df['BB_Upper'].iloc[-1]
        bb_lower = spx_df['BB_Lower'].iloc[-1]
        bb_range = bb_upper - bb_lower
        position_pct = ((current_price - bb_lower) / bb_range) * 100

        print(f"\nBollinger Band Position:")
        print(f"  Price is at {position_pct:.1f}% within the BB range")
        if position_pct > 80:
            print(f"  → Near upper band (potentially overbought)")
        elif position_pct < 20:
            print(f"  → Near lower band (potentially oversold)")
        else:
            print(f"  → Within normal range")

        # EMA vs SMA comparison
        ema_val = spx_df['EMA'].iloc[-1]
        sma_val = spx_df['SMA'].iloc[-1]
        print(f"\nMoving Average Comparison:")
        if ema_val > sma_val:
            print(f"  EMA > SMA by ${ema_val - sma_val:.2f} (bullish short-term momentum)")
        else:
            print(f"  EMA < SMA by ${sma_val - ema_val:.2f} (bearish short-term momentum)")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        raise

    finally:
        ts_store.close()

    print("\n" + "="*70)


if __name__ == "__main__":
    chart_spx_with_indicators()
