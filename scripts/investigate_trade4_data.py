"""Investigate data quality issues for Trade #4 on Nov 20, 2025."""

import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.data.timescale_store import TimescaleStore
import pandas as pd


def main():
    """Investigate Trade #4 data quality."""

    print("="*70)
    print("TRADE #4 DATA QUALITY INVESTIGATION")
    print("="*70)

    ts_store = TimescaleStore()

    # Trade #4 details from backtest
    entry_time = datetime(2025, 11, 20, 14, 49, 0)
    exit_time = datetime(2025, 11, 20, 17, 3, 0)
    entry_price = 6712.50

    print(f"\nTrade Details:")
    print(f"  Entry: {entry_time}")
    print(f"  Exit: {exit_time}")
    print(f"  SPX @ Entry: ${entry_price:.2f}")
    print(f"  Entry Cost: -$1,500 (credit received)")
    print(f"  Exit Value shown: $84,120 (SUSPICIOUS)")

    # Get options data at entry
    print("\n" + "="*70)
    print("OPTIONS DATA AT ENTRY")
    print("="*70)

    options_entry = ts_store.get_options_for_backtest(
        underlying_ticker='SPX',
        start_time=entry_time,
        end_time=entry_time,
        min_dte=0,
        max_dte=0,
    )

    # Strategy picks strike just below current price
    # With SPX at 6712.50, it would pick ~6710 as short strike
    # And 6700 as long strike (10 points lower)

    print(f"\nTotal option contracts available: {len(options_entry)}")

    # Show puts around the likely strikes
    relevant_entry = options_entry[
        (options_entry['strike_price'] >= 6695) &
        (options_entry['strike_price'] <= 6715) &
        (options_entry['option_type'] == 'P')
    ].sort_values('strike_price')

    print(f"\nPut options 6695-6715 at entry:")
    print(relevant_entry[['contract_symbol', 'strike_price', 'open', 'high', 'low', 'close',
                          'volume', 'bid', 'ask', 'mark', 'bid_size', 'ask_size']].to_string())

    # Determine which strikes strategy would pick
    strikes_below = relevant_entry[relevant_entry['strike_price'] <= entry_price]
    if not strikes_below.empty:
        short_strike = strikes_below.iloc[-1]['strike_price']  # Highest strike below price
        long_strike = short_strike - 10

        print(f"\n📊 Strategy would pick:")
        print(f"   Short strike: {short_strike} (sell put)")
        print(f"   Long strike: {long_strike} (buy put)")

        short_put_entry = relevant_entry[relevant_entry['strike_price'] == short_strike].iloc[0]
        long_put_entry = relevant_entry[relevant_entry['strike_price'] == long_strike].iloc[0]

        print(f"\n   Short {short_strike} put @ entry:")
        print(f"      Mark: ${short_put_entry['mark']:.2f} (bid: ${short_put_entry['bid']:.2f}, ask: ${short_put_entry['ask']:.2f})")
        print(f"      Volume: {short_put_entry['volume']}")
        print(f"   Long {long_strike} put @ entry:")
        print(f"      Mark: ${long_put_entry['mark']:.2f} (bid: ${long_put_entry['bid']:.2f}, ask: ${long_put_entry['ask']:.2f})")
        print(f"      Volume: {long_put_entry['volume']}")

        net_credit = (short_put_entry['mark'] - long_put_entry['mark']) * 10 * 100
        print(f"\n   Net credit: ${net_credit:.2f}")
        print(f"   Expected entry_cost: -${net_credit:.2f}")

        if abs(net_credit - 1500) > 100:
            print(f"   ⚠️  WARNING: Expected ${net_credit:.2f} but backtest shows $1,500")

    # Get options data at exit
    print("\n" + "="*70)
    print("OPTIONS DATA AT EXIT")
    print("="*70)

    options_exit = ts_store.get_options_for_backtest(
        underlying_ticker='SPX',
        start_time=exit_time,
        end_time=exit_time,
        min_dte=0,
        max_dte=0,
    )

    print(f"\nTotal option contracts available: {len(options_exit)}")

    relevant_exit = options_exit[
        (options_exit['strike_price'] >= 6695) &
        (options_exit['strike_price'] <= 6715) &
        (options_exit['option_type'] == 'P')
    ].sort_values('strike_price')

    print(f"\nPut options 6695-6715 at exit:")
    print(relevant_exit[['contract_symbol', 'strike_price', 'open', 'high', 'low', 'close',
                         'volume', 'bid', 'ask', 'mark', 'bid_size', 'ask_size']].to_string())

    if not strikes_below.empty:
        short_put_exit = relevant_exit[relevant_exit['strike_price'] == short_strike]
        long_put_exit = relevant_exit[relevant_exit['strike_price'] == long_strike]

        print(f"\n📊 Position value at exit:")

        if short_put_exit.empty:
            print(f"   ❌ SHORT {short_strike} PUT: NO DATA AT EXIT")
            print(f"      This is the problem! Missing price data causes incorrect valuation")
        else:
            short_exit = short_put_exit.iloc[0]
            print(f"   Short {short_strike} put @ exit:")
            print(f"      Mark: ${short_exit['mark']:.2f} (bid: ${short_exit['bid']:.2f}, ask: ${short_exit['ask']:.2f})")
            print(f"      Volume: {short_exit['volume']}")
            print(f"      Value: -10 contracts × ${short_exit['mark']:.2f} × 100 = -${short_exit['mark'] * 10 * 100:,.2f}")

        if long_put_exit.empty:
            print(f"   ❌ LONG {long_strike} PUT: NO DATA AT EXIT")
            print(f"      This is the problem! Missing price data causes incorrect valuation")
        else:
            long_exit = long_put_exit.iloc[0]
            print(f"   Long {long_strike} put @ exit:")
            print(f"      Mark: ${long_exit['mark']:.2f} (bid: ${long_exit['bid']:.2f}, ask: ${long_exit['ask']:.2f})")
            print(f"      Volume: {long_exit['volume']}")
            print(f"      Value: +10 contracts × ${long_exit['mark']:.2f} × 100 = +${long_exit['mark'] * 10 * 100:,.2f}")

        if not short_put_exit.empty and not long_put_exit.empty:
            position_value = (-short_exit['mark'] + long_exit['mark']) * 10 * 100
            print(f"\n   Total position value: ${position_value:,.2f}")
            pnl = position_value - (-net_credit)
            print(f"   P&L: ${pnl:,.2f} ({pnl/net_credit*100:.2f}%)")

            if abs(position_value - 84120) > 1000:
                print(f"\n   ⚠️  MISMATCH: Calculated ${position_value:,.2f} but backtest shows $84,120")

    # Check for missing contracts throughout the day
    print("\n" + "="*70)
    print("DATA COMPLETENESS CHECK")
    print("="*70)

    # Get all data for Nov 20
    start_day = datetime(2025, 11, 20, 14, 30)  # Market open
    end_day = datetime(2025, 11, 20, 16, 0)  # Market close

    all_day_data = ts_store.get_options_for_backtest(
        underlying_ticker='SPX',
        start_time=start_day,
        end_time=end_day,
        min_dte=0,
        max_dte=0,
    )

    # Check if the specific contracts exist throughout the day
    if not strikes_below.empty:
        short_symbol = short_put_entry['contract_symbol']
        long_symbol = long_put_entry['contract_symbol']

        short_data = all_day_data[all_day_data['contract_symbol'] == short_symbol]
        long_data = all_day_data[all_day_data['contract_symbol'] == long_symbol]

        print(f"\n{short_symbol} (short leg):")
        print(f"  Total timestamps: {len(short_data)}")
        print(f"  Missing mark prices: {short_data['mark'].isna().sum()}")
        print(f"  Zero mark prices: {(short_data['mark'] == 0).sum()}")

        print(f"\n{long_symbol} (long leg):")
        print(f"  Total timestamps: {len(long_data)}")
        print(f"  Missing mark prices: {long_data['mark'].isna().sum()}")
        print(f"  Zero mark prices: {(long_data['mark'] == 0).sum()}")

        # Check specific timestamps around exit
        print(f"\n{short_symbol} prices around exit time:")
        exit_window_start = exit_time - timedelta(minutes=5)
        exit_window_end = exit_time + timedelta(minutes=5)

        short_around_exit = short_data[
            (short_data['timestamp'] >= exit_window_start) &
            (short_data['timestamp'] <= exit_window_end)
        ].sort_values('timestamp')

        if not short_around_exit.empty:
            print(short_around_exit[['timestamp', 'mark', 'bid', 'ask', 'volume']].to_string())
        else:
            print("  ❌ NO DATA in exit window!")

        print(f"\n{long_symbol} prices around exit time:")
        long_around_exit = long_data[
            (long_data['timestamp'] >= exit_window_start) &
            (long_data['timestamp'] <= exit_window_end)
        ].sort_values('timestamp')

        if not long_around_exit.empty:
            print(long_around_exit[['timestamp', 'mark', 'bid', 'ask', 'volume']].to_string())
        else:
            print("  ❌ NO DATA in exit window!")

    # Check data source
    print("\n" + "="*70)
    print("DATA SOURCE ANALYSIS")
    print("="*70)

    print(f"\nData sources in Nov 20 data:")
    print(all_day_data['data_source'].value_counts())

    print(f"\nBid/Ask spread statistics:")
    all_day_data['spread_pct'] = ((all_day_data['ask'] - all_day_data['bid']) / all_day_data['mark'] * 100)
    print(f"  Mean spread: {all_day_data['spread_pct'].mean():.2f}%")
    print(f"  Median spread: {all_day_data['spread_pct'].median():.2f}%")
    print(f"  Max spread: {all_day_data['spread_pct'].max():.2f}%")
    print(f"  Min spread: {all_day_data['spread_pct'].min():.2f}%")

    # Check for wide spreads that might indicate bad data
    wide_spreads = all_day_data[all_day_data['spread_pct'] > 50]
    print(f"\nContracts with >50% bid/ask spread: {len(wide_spreads)}")
    if len(wide_spreads) > 0:
        print("\nSample wide spreads:")
        print(wide_spreads[['timestamp', 'contract_symbol', 'strike_price', 'bid', 'ask', 'mark', 'spread_pct']].head(10).to_string())

    ts_store.close()

    print("\n" + "="*70)
    print("INVESTIGATION COMPLETE")
    print("="*70)


if __name__ == "__main__":
    main()
