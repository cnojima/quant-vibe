"""Chart today's SPXW options data from schwab_poll.

This script creates visualizations of options data collected today including:
- SPX price over time (derived from ATM options)
- Options volume and activity
- Bid/ask spreads
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.data.timescale_store import TimescaleStore


def chart_today_options():
    """Create charts for today's options data."""

    ts_store = TimescaleStore()

    print("="*70)
    print("CHARTING TODAY'S SPXW OPTIONS DATA")
    print("="*70)

    # Get date range - check yesterday since data might be from Dec 15
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)
    data_start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
    data_end = now

    print(f"\nFetching data from {data_start} to {data_end}")
    print("(Note: Times will be converted to Eastern Time for display)")
    print("(Looking at last 24 hours to capture available data)")

    try:
        # Get all options data for today from schwab_poll
        query = """
        SELECT
            timestamp,
            option_ticker,
            strike_price,
            contract_type,
            close,
            volume,
            bid,
            ask,
            delta,
            implied_volatility
        FROM options_bars
        WHERE data_source = 'schwab_poll'
            AND timestamp >= %s
            AND timestamp <= %s
        ORDER BY timestamp, strike_price
        """

        with ts_store.get_connection() as conn:
            df = pd.read_sql_query(
                query,
                conn,
                params=[data_start, data_end],
                parse_dates=['timestamp']
            )

        if df.empty:
            print("\n❌ No data found for today")
            print("Make sure the polling script is running and has collected data.")
            return

        print(f"\n✅ Found {len(df)} option bars")
        print(f"Time range: {df['timestamp'].min()} to {df['timestamp'].max()}")
        print(f"Unique contracts: {df['option_ticker'].nunique()}")

        # Convert timestamps to Eastern Time for display
        df['timestamp_et'] = df['timestamp'].dt.tz_convert('America/New_York')

        # Calculate bid/ask spread percentage
        df['spread_pct'] = ((df['ask'] - df['bid']) / df['close'] * 100).clip(upper=100)

        # Get ATM options to estimate SPX price
        atm_data = []
        for ts in df['timestamp'].unique():
            ts_data = df[df['timestamp'] == ts]

            # Find closest to ATM (delta near 0.5 for calls, -0.5 for puts)
            calls = ts_data[ts_data['contract_type'] == 'call'].copy()
            puts = ts_data[ts_data['contract_type'] == 'put'].copy()

            if not calls.empty:
                calls['delta_diff'] = (calls['delta'] - 0.5).abs()
                atm_call = calls.nsmallest(1, 'delta_diff')
                if not atm_call.empty:
                    atm_data.append({
                        'timestamp': ts,
                        'timestamp_et': atm_call.iloc[0]['timestamp_et'],
                        'spx_price': atm_call.iloc[0]['strike_price'],
                        'type': 'call'
                    })

        atm_df = pd.DataFrame(atm_data)

        # Create figure with subplots
        fig, axes = plt.subplots(3, 1, figsize=(14, 10))
        fig.suptitle(f"SPXW Options Data - {now.strftime('%Y-%m-%d')}", fontsize=16, fontweight='bold')

        # Plot 1: SPX Price (from ATM strikes)
        if not atm_df.empty:
            ax1 = axes[0]
            ax1.plot(atm_df['timestamp_et'], atm_df['spx_price'],
                    linewidth=2, color='blue', marker='o', markersize=4)
            ax1.set_ylabel('SPX Price', fontsize=12, fontweight='bold')
            ax1.set_title('SPX Price (Estimated from ATM Options)', fontsize=11)
            ax1.grid(True, alpha=0.3)
            ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz='America/New_York'))
            ax1.tick_params(axis='x', rotation=45)

        # Plot 2: Total Volume by Time
        ax2 = axes[1]
        volume_by_time = df.groupby('timestamp_et')['volume'].sum()
        ax2.bar(volume_by_time.index, volume_by_time.values,
               width=0.0005, color='green', alpha=0.7)
        ax2.set_ylabel('Total Volume', fontsize=12, fontweight='bold')
        ax2.set_title('Options Volume', fontsize=11)
        ax2.grid(True, alpha=0.3)
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz='America/New_York'))
        ax2.tick_params(axis='x', rotation=45)

        # Plot 3: Bid/Ask Spread
        ax3 = axes[2]
        spread_by_time = df.groupby('timestamp_et')['spread_pct'].mean()
        ax3.plot(spread_by_time.index, spread_by_time.values,
                linewidth=2, color='red', marker='o', markersize=3)
        ax3.set_ylabel('Avg Spread %', fontsize=12, fontweight='bold')
        ax3.set_xlabel('Time (Eastern)', fontsize=12, fontweight='bold')
        ax3.set_title('Average Bid/Ask Spread %', fontsize=11)
        ax3.grid(True, alpha=0.3)
        ax3.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz='America/New_York'))
        ax3.tick_params(axis='x', rotation=45)

        plt.tight_layout()

        # Save chart
        output_file = Path(__file__).parent.parent / "data" / f"spxw_today_{now.strftime('%Y%m%d')}.png"
        output_file.parent.mkdir(exist_ok=True)
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        print(f"\n✅ Chart saved to: {output_file}")

        # Show statistics
        print("\nData Summary:")
        print(f"  Time Range (ET): {df['timestamp_et'].min().strftime('%H:%M')} - {df['timestamp_et'].max().strftime('%H:%M')}")
        print(f"  Total Bars: {len(df)}")
        print(f"  Unique Contracts: {df['option_ticker'].nunique()}")
        print(f"  Calls: {len(df[df['contract_type'] == 'call'])}")
        print(f"  Puts: {len(df[df['contract_type'] == 'put'])}")
        print(f"  Avg Spread: {df['spread_pct'].mean():.2f}%")
        print(f"  Total Volume: {df['volume'].sum():,.0f}")

        if not atm_df.empty:
            print(f"\nSPX Price Range:")
            print(f"  Low: ${atm_df['spx_price'].min():.2f}")
            print(f"  High: ${atm_df['spx_price'].max():.2f}")
            print(f"  Current: ${atm_df['spx_price'].iloc[-1]:.2f}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise

    finally:
        ts_store.close()


if __name__ == "__main__":
    chart_today_options()
