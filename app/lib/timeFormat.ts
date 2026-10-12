/**
 * app/lib/timeFormat.ts
 * Shared time-formatting utilities used across dashboard components.
 */

/**
 * Converts a raw minutes value to a human-readable "Xhr Ymin" string.
 * Examples:
 *   75  → "1hr 15min"
 *   30  → "30min"
 *   120 → "2hr"
 *   0   → "0min"
 */
export function formatMinutesToHrMin(minutes: number): string {
  if (!minutes || minutes <= 0) return '0min';
  const hrs = Math.floor(minutes / 60);
  const mins = Math.round(minutes % 60);
  if (hrs === 0) return `${mins}min`;
  if (mins === 0) return `${hrs}hr`;
  return `${hrs}hr ${mins}min`;
}

/**
 * Converts minutes to a short clock-style string "H:MM".
 * Examples:
 *   75  → "1:15"
 *   30  → "0:30"
 *   120 → "2:00"
 */
export function formatMinutesToClock(minutes: number): string {
  if (!minutes || minutes <= 0) return '0:00';
  const hrs = Math.floor(minutes / 60);
  const mins = Math.round(minutes % 60);
  return `${hrs}:${String(mins).padStart(2, '0')}`;
}

/**
 * Returns a relative time label for a timestamp.
 * Examples: "2 min ago", "1 hr ago", "3 days ago"
 */
export function timeAgo(date: Date | string): string {
  const d = typeof date === 'string' ? new Date(date) : date;
  const diffMs = Date.now() - d.getTime();
  const diffMin = Math.floor(diffMs / 60_000);
  if (diffMin < 1) return 'just now';
  if (diffMin < 60) return `${diffMin} min ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr} hr ago`;
  const diffDay = Math.floor(diffHr / 24);
  return `${diffDay} day${diffDay !== 1 ? 's' : ''} ago`;
}

/**
 * Formats an ISO datetime string into a locale-friendly display.
 * Example: "12 May 2026, 09:30 AM"
 */
export function formatDateTime(date: Date | string): string {
  const d = typeof date === 'string' ? new Date(date) : date;
  return d.toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
  });
}
