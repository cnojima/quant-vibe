/**
 * Date utilities for handling EST (US Eastern Time) dates.
 *
 * All trading happens in EST, so we need to ensure the UI
 * uses EST dates, not the user's local timezone or UTC.
 */

/**
 * Get current date/time in EST timezone.
 */
export function getESTDate(): Date {
  // Create date in EST using Intl.DateTimeFormat
  const estString = new Date().toLocaleString('en-US', {
    timeZone: 'America/New_York',
  });
  return new Date(estString);
}

/**
 * Format a Date object as YYYY-MM-DD string.
 */
export function formatDateForInput(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

/**
 * Get today's date in EST as YYYY-MM-DD string.
 * If today is a weekend, returns the most recent Friday.
 */
export function getTodayEST(): string {
  const est = getESTDate();

  // If weekend, use last Friday
  if (est.getDay() === 0) {
    // Sunday - use Friday
    est.setDate(est.getDate() - 2);
  } else if (est.getDay() === 6) {
    // Saturday - use Friday
    est.setDate(est.getDate() - 1);
  }

  return formatDateForInput(est);
}

/**
 * Get yesterday's trading date in EST as YYYY-MM-DD string.
 * Skips weekends automatically.
 */
export function getYesterdayEST(): string {
  const est = getESTDate();
  est.setDate(est.getDate() - 1);

  // If yesterday was a weekend, go back to Friday
  while (est.getDay() === 0 || est.getDay() === 6) {
    est.setDate(est.getDate() - 1);
  }

  return formatDateForInput(est);
}

/**
 * Get the start and end of this week (Monday to today or Friday) in EST.
 * Returns { start: 'YYYY-MM-DD', end: 'YYYY-MM-DD' }
 */
export function getThisWeekEST(): { start: string; end: string } {
  const est = getESTDate();
  const dayOfWeek = est.getDay();

  // Calculate days since Monday (1 = Monday, 0 = Sunday)
  const daysSinceMonday = dayOfWeek === 0 ? 6 : dayOfWeek - 1;

  const startOfWeek = new Date(est);
  startOfWeek.setDate(est.getDate() - daysSinceMonday);

  // If today is Saturday or Sunday, use last Friday as end
  const endOfWeek = new Date(est);
  if (dayOfWeek === 0) {
    // Sunday - use Friday
    endOfWeek.setDate(est.getDate() - 2);
  } else if (dayOfWeek === 6) {
    // Saturday - use Friday
    endOfWeek.setDate(est.getDate() - 1);
  }

  return {
    start: formatDateForInput(startOfWeek),
    end: formatDateForInput(endOfWeek),
  };
}

/**
 * Get the start and end of last week (last Monday to last Friday) in EST.
 * Returns { start: 'YYYY-MM-DD', end: 'YYYY-MM-DD' }
 */
export function getLastWeekEST(): { start: string; end: string } {
  const est = getESTDate();
  const dayOfWeek = est.getDay();

  // Calculate days to go back to get to last Monday
  let daysToLastMonday = dayOfWeek === 0 ? 6 : dayOfWeek - 1;
  daysToLastMonday += 7; // Go back one more week

  const lastMonday = new Date(est);
  lastMonday.setDate(est.getDate() - daysToLastMonday);

  // Last Friday is 4 days after last Monday
  const lastFriday = new Date(lastMonday);
  lastFriday.setDate(lastMonday.getDate() + 4);

  return {
    start: formatDateForInput(lastMonday),
    end: formatDateForInput(lastFriday),
  };
}

/**
 * Get a date range going back N days from today (EST).
 * Returns { start: 'YYYY-MM-DD', end: 'YYYY-MM-DD' }
 */
export function getLastNDaysEST(days: number): { start: string; end: string } {
  const end = getESTDate();
  const start = new Date(end);
  start.setDate(start.getDate() - days);

  return {
    start: formatDateForInput(start),
    end: formatDateForInput(end),
  };
}

/**
 * Get a date range going back N months from today (EST).
 * Returns { start: 'YYYY-MM-DD', end: 'YYYY-MM-DD' }
 */
export function getLastNMonthsEST(months: number): { start: string; end: string } {
  const end = getESTDate();
  const start = new Date(end);
  start.setMonth(start.getMonth() - months);

  return {
    start: formatDateForInput(start),
    end: formatDateForInput(end),
  };
}

/**
 * Get a date range going back N years from today (EST).
 * Returns { start: 'YYYY-MM-DD', end: 'YYYY-MM-DD' }
 */
export function getLastNYearsEST(years: number): { start: string; end: string } {
  const end = getESTDate();
  const start = new Date(end);
  start.setFullYear(start.getFullYear() - years);

  return {
    start: formatDateForInput(start),
    end: formatDateForInput(end),
  };
}
