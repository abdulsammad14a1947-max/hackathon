/**
 * Consistent formatting helpers: en-GB dates, PKR-style "Rs 123,456" money,
 * plain numbers and hours. All helpers are null-safe and never throw.
 */

const dateFmt = new Intl.DateTimeFormat("en-GB", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});

const dateTimeFmt = new Intl.DateTimeFormat("en-GB", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

const moneyFmt = new Intl.NumberFormat("en-GB", {
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
});

const numberFmt = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 2 });

/** Parses "YYYY-MM-DD" as a local date to avoid UTC timezone day-shift. */
function parseDate(value: string | number | Date): Date | null {
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value;
  if (typeof value === "number") {
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? null : d;
  }
  const s = String(value).trim();
  if (!s) return null;
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
  if (dateOnly) {
    const [, y, m, d] = dateOnly;
    return new Date(Number(y), Number(m) - 1, Number(d));
  }
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function fmtDate(value?: string | number | Date | null): string {
  if (value === null || value === undefined || value === "") return "—";
  const d = parseDate(value);
  return d ? dateFmt.format(d) : "—";
}

export function fmtDateTime(value?: string | number | Date | null): string {
  if (value === null || value === undefined || value === "") return "—";
  const d = parseDate(value);
  return d ? dateTimeFmt.format(d) : "—";
}

/** Formats a time-only value such as "09:30:00" or a full ISO timestamp. */
export function fmtTime(value?: string | null): string {
  if (!value) return "—";
  const m = /(\d{2}):(\d{2})/.exec(value);
  if (m) return `${m[1]}:${m[2]}`;
  return value;
}

export function fmtMoney(value?: number | string | null): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(n)) return "—";
  return `Rs ${moneyFmt.format(n)}`;
}

export function fmtNumber(value?: number | string | null, suffix = ""): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(n)) return "—";
  return `${numberFmt.format(n)}${suffix}`;
}

export function fmtHours(value?: number | string | null): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(n)) return "—";
  return `${numberFmt.format(n)} h`;
}

export const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

export function monthName(month: number): string {
  return MONTHS[(month - 1 + 12) % 12] ?? String(month);
}

export function todayISO(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export function currentYear(): number {
  return new Date().getFullYear();
}

export function isoDay(date: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())}`;
}
