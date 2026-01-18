/**
 * Date utilities for handling EST (US Eastern Time) dates.
 * All trading happens in EST, so we ensure the UI uses EST dates.
 */

const EST_TIMEZONE = 'America/New_York';

/**
 * Get current date/time in EST timezone.
 */
export function getESTDate(): Date {
  const estString = new Date().toLocaleString('en-US', {
    timeZone: EST_TIMEZONE,
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
 * Check if a date is a weekend.
 */
function isWeekend(date: Date): boolean {
  const day = date.getDay();
  return day === 0 || day === 6;
}

/**
 * Get the most recent trading day (skips weekends).
 */
function getMostRecentTradingDay(date: Date): Date {
  const result = new Date(date);
  while (isWeekend(result)) {
    result.setDate(result.getDate() - 1);
  }
  return result;
}

/**
 * Get today's date in EST as YYYY-MM-DD string.
 * If today is a weekend, returns the most recent Friday.
 */
export function getTodayEST(): string {
  const est = getESTDate();
  return formatDateForInput(getMostRecentTradingDay(est));
}

/**
 * Get yesterday's trading date in EST as YYYY-MM-DD string.
 * Skips weekends automatically.
 */
export function getYesterdayEST(): string {
  const est = getESTDate();
  est.setDate(est.getDate() - 1);
  return formatDateForInput(getMostRecentTradingDay(est));
}

/**
 * Get the start and end of this week (Monday to today or Friday) in EST.
 */
export function getThisWeekEST(): { start: string; end: string } {
  const est = getESTDate();
  const dayOfWeek = est.getDay();
  const daysSinceMonday = dayOfWeek === 0 ? 6 : dayOfWeek - 1;

  const startOfWeek = new Date(est);
  startOfWeek.setDate(est.getDate() - daysSinceMonday);

  const endOfWeek = getMostRecentTradingDay(est);

  return {
    start: formatDateForInput(startOfWeek),
    end: formatDateForInput(endOfWeek),
  };
}

/**
 * Get the start and end of last week (last Monday to last Friday) in EST.
 */
export function getLastWeekEST(): { start: string; end: string } {
  const est = getESTDate();
  const dayOfWeek = est.getDay();
  const daysToLastMonday = (dayOfWeek === 0 ? 6 : dayOfWeek - 1) + 7;

  const lastMonday = new Date(est);
  lastMonday.setDate(est.getDate() - daysToLastMonday);

  const lastFriday = new Date(lastMonday);
  lastFriday.setDate(lastMonday.getDate() + 4);

  return {
    start: formatDateForInput(lastMonday),
    end: formatDateForInput(lastFriday),
  };
}

/**
 * Get a date range going back N days from today (EST).
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
 * @param months - Number of months to go back
 * @param offsetMonths - Optional offset from today
 */
export function getLastNMonthsEST(
  months: number,
  offsetMonths = 0
): { start: string; end: string } {
  const end = getESTDate();
  end.setMonth(end.getMonth() - offsetMonths);

  const start = new Date(end);
  start.setMonth(start.getMonth() - months);

  return {
    start: formatDateForInput(start),
    end: formatDateForInput(end),
  };
}

/**
 * Get a date range going back N years from today (EST).
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