/**
 * The month grid behind the range picker.
 *
 * Kept apart from the card and free of any DOM reference, because the fiddly
 * parts are here and none of them need a browser: which day a week starts on
 * differs by country, a month grid has to be padded at both ends, and "is this
 * day inside the selection" is asked forty-two times per render.
 *
 * Everything works in local time. A date is identified by its `YYYY-MM-DD`
 * string rather than by a timestamp -- that is what the range fields hold, and
 * it sidesteps every question about when a day begins in which zone.
 */

/** `YYYY-MM-DD` in local time, the same form `<input type="date">` produces. */
export function isoDate(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/**
 * Which weekday a week starts on, 0 = Sunday.
 *
 * `Intl.Locale.weekInfo` knows this and is not everywhere yet, so a miss falls
 * back to Monday -- right for most of the world, and wrong in a way that only
 * shifts the columns rather than the dates.
 */
export function firstDayOfWeek(locale: string): number {
  try {
    const info = (new Intl.Locale(locale) as unknown as { weekInfo?: { firstDay?: number } })
      .weekInfo;
    const first = info?.firstDay;
    // The standard counts Monday as 1 and Sunday as 7; JavaScript counts Sunday
    // as 0, which is the one place these two disagree.
    if (typeof first === "number") return first === 7 ? 0 : first;
  } catch {
    // An unparsable locale is no reason to refuse to draw a calendar.
  }
  return 1;
}

/** Short weekday names, starting on the day that locale starts its week. */
export function weekdayLabels(locale: string, firstDay = firstDayOfWeek(locale)): string[] {
  const format = new Intl.DateTimeFormat(locale, { weekday: "short" });
  // 4 January 1970 was a Sunday, which makes the arithmetic below trivial.
  return Array.from({ length: 7 }, (_, i) =>
    format.format(new Date(1970, 0, 4 + ((firstDay + i) % 7)))
  );
}

/** "September 2026", as that locale writes it. */
export function monthLabel(locale: string, year: number, month: number): string {
  return new Intl.DateTimeFormat(locale, { month: "long", year: "numeric" }).format(
    new Date(year, month, 1)
  );
}

export interface GridDay {
  date: Date;
  iso: string;
  /** False for the days either side that only fill the first and last row. */
  inMonth: boolean;
}

/**
 * Six weeks of days covering the month, padded with its neighbours.
 *
 * Always six rows, never five or four: a grid that changes height makes the
 * buttons below it jump as the user pages through the months.
 */
export function monthGrid(year: number, month: number, firstDay: number): GridDay[] {
  const first = new Date(year, month, 1);
  const lead = (first.getDay() - firstDay + 7) % 7;
  const start = new Date(year, month, 1 - lead);

  return Array.from({ length: 42 }, (_, i) => {
    const date = new Date(start.getFullYear(), start.getMonth(), start.getDate() + i);
    return { date, iso: isoDate(date), inMonth: date.getMonth() === month };
  });
}

/** Where a day sits in the chosen span, for the highlighting. */
export type DayRole = "none" | "start" | "end" | "between" | "single";

export function dayRole(iso: string, from: string, to: string): DayRole {
  if (!from) return "none";
  const [a, b] = !to || to >= from ? [from, to] : [to, from];
  if (!b) return iso === a ? "single" : "none";
  if (iso === a && iso === b) return "single";
  if (iso === a) return "start";
  if (iso === b) return "end";
  return iso > a && iso < b ? "between" : "none";
}

/**
 * What one click does.
 *
 * First click picks a day. The next extends it to a span. A click after that
 * starts over, which is what a third click means when the first two already
 * said everything.
 */
export function nextSelection(
  current: { from: string; to: string },
  clicked: string
): { from: string; to: string } {
  if (!current.from || current.to) return { from: clicked, to: "" };
  return { from: current.from, to: clicked };
}
