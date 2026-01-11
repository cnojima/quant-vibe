import pandas as pd
from datetime import datetime, timedelta

# Read the CSV
df = pd.read_csv('/Users/curisu/dev/quant-vibe/src/quant_vibe/data/sanity/underlying_bars.csv')
df['date'] = pd.to_datetime(df['date'])
df = df.sort_values('date')

# Get all dates in the data
dates = df['date'].tolist()

# Known US market holidays (non-exhaustive, but covers major ones)
holidays_2023 = [
    '2023-01-02',  # New Year's (observed)
    '2023-01-16',  # MLK Day
    '2023-02-20',  # Presidents' Day
    '2023-04-07',  # Good Friday
    '2023-05-29',  # Memorial Day
    '2023-06-19',  # Juneteenth
    '2023-07-04',  # Independence Day
    '2023-09-04',  # Labor Day
    '2023-11-23',  # Thanksgiving
    '2023-12-25',  # Christmas
]

holidays_2024 = [
    '2024-01-01',  # New Year's Day
    '2024-01-15',  # MLK Day
    '2024-02-19',  # Presidents' Day
    '2024-03-29',  # Good Friday
    '2024-05-27',  # Memorial Day
    '2024-06-19',  # Juneteenth
    '2024-07-04',  # Independence Day
    '2024-09-02',  # Labor Day
    '2024-11-28',  # Thanksgiving
    '2024-12-25',  # Christmas
]

holidays_2025 = [
    '2025-01-01',  # New Year's Day
    '2025-01-20',  # MLK Day
    '2025-02-17',  # Presidents' Day
    '2025-04-18',  # Good Friday
    '2025-05-26',  # Memorial Day
    '2025-06-19',  # Juneteenth
    '2025-07-04',  # Independence Day
    '2025-09-01',  # Labor Day
    '2025-11-27',  # Thanksgiving
    '2025-12-25',  # Christmas
]

holidays_2026 = [
    '2026-01-01',  # New Year's Day
]

all_holidays = set(pd.to_datetime(holidays_2023 + holidays_2024 + holidays_2025 + holidays_2026))

# Check for gaps between consecutive dates
print("=" * 80)
print("GAPS IN DATA (missing trading days between consecutive records)")
print("=" * 80)

for i in range(len(dates) - 1):
    current = dates[i]
    next_date = dates[i + 1]

    # Calculate expected next trading day
    check_date = current + timedelta(days=1)

    missing_days = []
    while check_date < next_date:
        # Skip weekends and holidays
        if check_date.weekday() < 5 and check_date not in all_holidays:  # Mon-Fri
            missing_days.append(check_date)
        check_date += timedelta(days=1)

    if missing_days:
        print(f"\nGap between {current.date()} and {next_date.date()}:")
        for missing in missing_days:
            day_name = missing.strftime('%A')
            print(f"  Missing: {missing.date()} ({day_name})")

print("\n" + "=" * 80)
print("DATA SUMMARY")
print("=" * 80)
print(f"First date: {dates[0].date()}")
print(f"Last date: {dates[-1].date()}")
print(f"Total dates in data: {len(dates)}")

# Calculate expected trading days
start = dates[0]
end = dates[-1]
expected_count = 0
check_date = start
while check_date <= end:
    if check_date.weekday() < 5 and check_date not in all_holidays:
        expected_count += 1
    check_date += timedelta(days=1)

print(f"Expected trading days: ~{expected_count}")
print(f"Missing trading days: ~{expected_count - len(dates)}")
