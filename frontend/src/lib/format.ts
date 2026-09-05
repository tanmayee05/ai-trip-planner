import { format, parseISO } from "date-fns";

/** "2026-09-15" -> "Tue, 15 Sep 2026" */
export function prettyDate(iso: string): string {
  try {
    return format(parseISO(iso), "EEE, d MMM yyyy");
  } catch {
    return iso;
  }
}

/** ISO timestamp -> "15 Sep, 3:44 pm" */
export function prettyDateTime(iso: string): string {
  try {
    return format(parseISO(iso), "d MMM, h:mm a");
  } catch {
    return iso;
  }
}

/** "2026-09-15 14:10+05:30" or "14:10" -> "14:10" */
export function clockTime(value: string | null | undefined): string {
  if (!value) return "--:--";
  const m = value.match(/(\d{1,2}:\d{2})/);
  return m ? m[1] : value;
}

/** today's date as YYYY-MM-DD, for <input type="date"> min/default */
export function todayISO(): string {
  return format(new Date(), "yyyy-MM-dd");
}
