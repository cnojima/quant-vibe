"""DateTime utility functions for backtesting.

All dates use US Eastern Time (EST/EDT) for market hours.
Trading day hours: 9:30 AM - 4:00 PM EST.
"""

from datetime import datetime, timedelta, timezone
from typing import Tuple
from zoneinfo import ZoneInfo


# US Eastern timezone for market hours
EST = ZoneInfo("America/New_York")

# Market hours in EST
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 30
MARKET_CLOSE_HOUR = 16
MARKET_CLOSE_MINUTE = 0


def make_utc_datetime(
    year: int,
    month: int,
    day: int,
    hour: int = 0,
    minute: int = 0,
    second: int = 0,
) -> datetime:
    """Create timezone-aware datetime in UTC.

    Args:
        year: Year
        month: Month
        day: Day
        hour: Hour (default: 0)
        minute: Minute (default: 0)
        second: Second (default: 0)

    Returns:
        Timezone-aware datetime in UTC
    """
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def trading_day_to_utc(year: int, month: int, day: int) -> Tuple[datetime, datetime]:
    """Convert a trading day to UTC market hours range.

    Given a calendar date, returns the market hours (9:30 AM - 4:00 PM EST)
    for that trading day in UTC.

    Args:
        year: Year
        month: Month
        day: Day

    Returns:
        Tuple of (market_open_utc, market_close_utc) as timezone-aware datetime objects

    Example:
        For Dec 22, 2025:
        - Market open:  Dec 22 09:30:00 EST = Dec 22 14:30:00 UTC
        - Market close: Dec 22 16:00:00 EST = Dec 22 21:00:00 UTC
    """
    # Create market open/close times in EST
    market_open_est = datetime(
        year, month, day, MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE, 0, tzinfo=EST
    )
    market_close_est = datetime(
        year, month, day, MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE, 0, tzinfo=EST
    )

    # Convert to UTC
    market_open_utc = market_open_est.astimezone(timezone.utc)
    market_close_utc = market_close_est.astimezone(timezone.utc)

    return market_open_utc, market_close_utc


def is_trading_day(year: int, month: int, day: int) -> bool:
    """Check if a date is a trading day (Monday-Friday, excluding holidays).

    Note: This is a simplified check that only excludes weekends.
    Market holidays are not currently excluded.

    Args:
        year: Year
        month: Month
        day: Day

    Returns:
        True if the date is a weekday, False if weekend
    """
    date = datetime(year, month, day)
    # Monday = 0, Sunday = 6
    return date.weekday() < 5  # Monday through Friday


def get_trading_days_in_range(
    start_year: int,
    start_month: int,
    start_day: int,
    end_year: int,
    end_month: int,
    end_day: int,
) -> list:
    """Get all trading days in a date range.

    Args:
        start_year: Start year
        start_month: Start month
        start_day: Start day
        end_year: End year
        end_month: End month
        end_day: End day

    Returns:
        List of (year, month, day) tuples for each trading day
    """
    start_date = datetime(start_year, start_month, start_day)
    end_date = datetime(end_year, end_month, end_day)

    trading_days = []
    current_date = start_date

    while current_date <= end_date:
        if is_trading_day(current_date.year, current_date.month, current_date.day):
            trading_days.append((current_date.year, current_date.month, current_date.day))
        current_date += timedelta(days=1)

    return trading_days


def get_date_range() -> Tuple[datetime, datetime]:
    """Prompt user to select date range for backtest.

    All dates are in EST (US Eastern Time) and constrained to market hours
    (9:30 AM - 4:00 PM EST). Weekends are automatically excluded.

    Returns:
        Tuple of (start_date, end_date) as timezone-aware datetime objects in UTC
    """
    print("=" * 70)
    print("SELECT DATE RANGE FOR BACKTEST")
    print("=" * 70)
    print()
    print("Available date range options:")
    print("  1. Today (market hours only)")
    print("  2. This week (Mon-Fri market hours)")
    print("  3. This month (trading days only)")
    print("  4. This quarter (trading days only)")
    print("  5. This year (trading days only)")
    print("  6. Custom date range (trading days only)")
    print()
    print("Note: All dates use US Eastern Time (EST)")
    print("      Market hours: 9:30 AM - 4:00 PM EST")
    print()

    while True:
        choice = input("Enter your choice (1-6): ").strip()

        if choice not in ["1", "2", "3", "4", "5", "6"]:
            print("Invalid choice. Please enter a number between 1 and 6.")
            continue

        # Get current date in EST
        now_est = datetime.now(EST)

        if choice == "1":  # Today (market hours only)
            start_date, end_date = trading_day_to_utc(now_est.year, now_est.month, now_est.day)

        elif choice == "2":  # This week (Monday to Friday)
            days_since_monday = now_est.weekday()
            monday = now_est - timedelta(days=days_since_monday)
            friday = monday + timedelta(days=4)  # Friday

            # Get all trading days this week
            trading_days = get_trading_days_in_range(
                monday.year,
                monday.month,
                monday.day,
                friday.year,
                friday.month,
                friday.day,
            )

            if trading_days:
                # Start of first trading day
                start_date, _ = trading_day_to_utc(*trading_days[0])
                # End of last trading day
                _, end_date = trading_day_to_utc(*trading_days[-1])
            else:
                print("No trading days found this week.")
                continue

        elif choice == "3":  # This month
            # First day of month
            first_day = datetime(now_est.year, now_est.month, 1)

            # Last day of month
            if now_est.month == 12:
                next_month = datetime(now_est.year + 1, 1, 1)
            else:
                next_month = datetime(now_est.year, now_est.month + 1, 1)
            last_day = next_month - timedelta(days=1)

            # Get all trading days this month
            trading_days = get_trading_days_in_range(
                first_day.year,
                first_day.month,
                first_day.day,
                last_day.year,
                last_day.month,
                last_day.day,
            )

            if trading_days:
                start_date, _ = trading_day_to_utc(*trading_days[0])
                _, end_date = trading_day_to_utc(*trading_days[-1])
            else:
                print("No trading days found this month.")
                continue

        elif choice == "4":  # This quarter
            # Q1: Jan-Mar, Q2: Apr-Jun, Q3: Jul-Sep, Q4: Oct-Dec
            quarter = (now_est.month - 1) // 3 + 1
            quarter_start_month = (quarter - 1) * 3 + 1
            quarter_end_month = quarter * 3

            # First day of quarter
            first_day = datetime(now_est.year, quarter_start_month, 1)

            # Last day of quarter
            if quarter_end_month == 12:
                next_quarter_start = datetime(now_est.year + 1, 1, 1)
            else:
                next_quarter_start = datetime(now_est.year, quarter_end_month + 1, 1)
            last_day = next_quarter_start - timedelta(days=1)

            # Get all trading days this quarter
            trading_days = get_trading_days_in_range(
                first_day.year,
                first_day.month,
                first_day.day,
                last_day.year,
                last_day.month,
                last_day.day,
            )

            if trading_days:
                start_date, _ = trading_day_to_utc(*trading_days[0])
                _, end_date = trading_day_to_utc(*trading_days[-1])
            else:
                print("No trading days found this quarter.")
                continue

        elif choice == "5":  # This year
            first_day = datetime(now_est.year, 1, 1)
            last_day = datetime(now_est.year, 12, 31)

            # Get all trading days this year
            trading_days = get_trading_days_in_range(
                first_day.year,
                first_day.month,
                first_day.day,
                last_day.year,
                last_day.month,
                last_day.day,
            )

            if trading_days:
                start_date, _ = trading_day_to_utc(*trading_days[0])
                _, end_date = trading_day_to_utc(*trading_days[-1])
            else:
                print("No trading days found this year.")
                continue

        elif choice == "6":  # Custom
            print()
            print("Enter custom date range (format: YYYY-MM-DD)")
            print("Note: Dates are in US Eastern Time")
            print("      Only trading days (Mon-Fri) will be included")

            while True:
                try:
                    start_str = input("Start date: ").strip()
                    start_parts = start_str.split("-")
                    start_y = int(start_parts[0])
                    start_m = int(start_parts[1])
                    start_d = int(start_parts[2])
                    break
                except (ValueError, IndexError):
                    print("Invalid date format. Please use YYYY-MM-DD (e.g., 2025-12-01)")

            while True:
                try:
                    end_str = input("End date: ").strip()
                    end_parts = end_str.split("-")
                    end_y = int(end_parts[0])
                    end_m = int(end_parts[1])
                    end_d = int(end_parts[2])

                    # Validate end >= start
                    if datetime(end_y, end_m, end_d) < datetime(start_y, start_m, start_d):
                        print("End date must be after start date. Please try again.")
                        continue
                    break
                except (ValueError, IndexError):
                    print("Invalid date format. Please use YYYY-MM-DD (e.g., 2025-12-15)")

            # Get all trading days in range
            trading_days = get_trading_days_in_range(start_y, start_m, start_d, end_y, end_m, end_d)

            if trading_days:
                start_date, _ = trading_day_to_utc(*trading_days[0])
                _, end_date = trading_day_to_utc(*trading_days[-1])
            else:
                print("No trading days found in that range.")
                continue

        # Confirm selection
        print()
        print(f"Selected date range: {start_date.date()} to {end_date.date()} (UTC)")
        print(
            f"Market hours: {start_date.strftime('%Y-%m-%d %H:%M')} to "
            f"{end_date.strftime('%Y-%m-%d %H:%M')} UTC"
        )
        confirm = input("Is this correct? (y/n): ").strip().lower()

        if confirm == "y":
            print()
            return start_date, end_date
        else:
            print()
            print("Let's try again...")
            print()
