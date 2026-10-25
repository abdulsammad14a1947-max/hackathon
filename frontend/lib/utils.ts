/**
 * Small defensive normalisers: the backend contract freezes field *names* but not
 * every list wrapper, so these helpers accept `{items:[...]}`, bare arrays and
 * plain objects and always give the UI something safe to render.
 */

export type Row = Record<string, unknown>;

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export function isObject(value: unknown): value is Row {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

/** Extracts a list of plain rows from a response value, or `[]`. */
export function asRows(value: unknown): Row[] {
  if (Array.isArray(value)) {
    return value.filter((v): v is Row => isObject(v));
  }
  if (isObject(value)) {
    const inner = value.items ?? value.data ?? value.results;
    if (Array.isArray(inner)) return asRows(inner);
  }
  return [];
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

/** Normalises paginated-or-bare-array list responses. */
export function asPage<T>(
  value: unknown,
  fallbackPage = 1,
  fallbackSize = 20,
): Page<T> {
  if (Array.isArray(value)) {
    const items = value as T[];
    return { items, total: items.length, page: 1, page_size: Math.max(items.length, 20) };
  }
  const o = isObject(value) ? value : {};
  const items = asRows(o.items ?? o.data ?? o.results) as unknown as T[];
  return {
    items,
    total: toNum(o.total, items.length),
    page: toNum(o.page, fallbackPage),
    page_size: toNum(o.page_size ?? o.pageSize ?? o.limit, fallbackSize),
  };
}

export function toNum(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "" && !Number.isNaN(Number(value))) {
    return Number(value);
  }
  return fallback;
}

export function toStr(value: unknown, fallback = ""): string {
  if (value === null || value === undefined) return fallback;
  if (typeof value === "object") {
    const o = value as Row;
    if (typeof o.name === "string") return o.name;
    if (typeof o.full_name === "string") return o.full_name;
    if (typeof o.label === "string") return o.label;
    return fallback;
  }
  return String(value);
}

export function toBool(value: unknown): boolean {
  return value === true || value === "true" || value === 1;
}

/** First key from `keys` that exists on the row. */
export function pick(row: Row | undefined | null, keys: string[]): unknown {
  if (!row) return undefined;
  for (const k of keys) {
    if (row[k] !== undefined && row[k] !== null) return row[k];
  }
  return undefined;
}

const LABEL_KEYS = [
  "name",
  "department",
  "dept",
  "department_name",
  "label",
  "code",
  "date",
  "key",
  "bucket",
  "month",
  "period",
];

const VALUE_KEYS = [
  "count",
  "value",
  "headcount",
  "total",
  "employees",
  "n",
  "amount",
  "cost",
  "late_count",
  "absent",
  "absenteeism",
];

export interface Pair {
  label: string;
  value: number;
}

/**
 * Normalises `[{name,count}]`, `{Engineering: 12}` and similar chart inputs
 * into `[{label, value}]`.
 */
export function asPairs(
  value: unknown,
  labelKeys: string[] = LABEL_KEYS,
  valueKeys: string[] = VALUE_KEYS,
): Pair[] {
  if (Array.isArray(value)) {
    const out: Pair[] = [];
    value.forEach((item, i) => {
      if (typeof item === "number") {
        out.push({ label: String(i + 1), value: item });
      } else if (isObject(item)) {
        const rawLabel = pick(item, labelKeys);
        const rawValue = pick(item, valueKeys);
        out.push({ label: toStr(rawLabel, `Item ${i + 1}`), value: toNum(rawValue, 0) });
      }
    });
    return out;
  }
  if (isObject(value)) {
    return Object.entries(value)
      .filter(([, v]) => typeof v === "number" || typeof v === "string")
      .map(([k, v]) => ({ label: k, value: toNum(v, 0) }));
  }
  return [];
}

/** Normalises a `[{date,present,...}]`-style series or number array. */
export function asSeries(
  value: unknown,
  valueKeys: string[] = ["present", "value", "count", "total"],
  labelKeys: string[] = ["date", "label", "day", "name"],
): Pair[] {
  return asPairs(value, labelKeys, valueKeys);
}

/** Normalises a "key → object/count" map used by leave utilization. */
export function asUtilization(value: unknown): {
  label: string;
  used: number;
  remaining: number;
  quota: number;
}[] {
  const rows = asRows(value);
  if (rows.length) {
    return rows.map((r, i) => {
      const used = toNum(pick(r, ["used", "taken", "avused", "approved"]), 0);
      const quota = toNum(pick(r, ["quota", "yearly_quota", "total"]), used);
      const remaining = toNum(
        pick(r, ["remaining", "left", "balance"]),
        Math.max(quota - used, 0),
      );
      return { label: toStr(pick(r, LABEL_KEYS), `Type ${i + 1}`), used, remaining, quota };
    });
  }
  if (isObject(value)) {
    return Object.entries(value).map(([k, v]) => {
      if (isObject(v)) {
        const used = toNum(pick(v, ["used", "taken"]), 0);
        const quota = toNum(pick(v, ["quota", "total"]), used);
        return {
          label: k,
          used,
          quota,
          remaining: toNum(pick(v, ["remaining", "left"]), Math.max(quota - used, 0)),
        };
      }
      const used = toNum(v, 0);
      return { label: k, used, quota: used, remaining: 0 };
    });
  }
  return [];
}

/** Normalises `string[]` or `[{text|insight|message}]` into bullets. */
export function asBullets(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value
      .map((v) => {
        if (typeof v === "string") return v;
        if (isObject(v)) {
          const s = toStr(pick(v, ["text", "insight", "message", "detail", "label"]), "");
          return s;
        }
        return "";
      })
      .filter(Boolean);
  }
  if (typeof value === "string" && value.trim()) return [value];
  return [];
}

export const WEEKDAYS = [
  "Sunday",
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
];

export const STATUS_TONE: Record<string, "ok" | "warn" | "danger" | "info" | "neutral"> = {
  present: "ok",
  active: "ok",
  approved: "ok",
  finalized: "ok",
  read: "ok",
  late: "warn",
  half_day: "warn",
  missing_checkout: "warn",
  pending: "warn",
  draft: "info",
  on_leave: "info",
  absent: "danger",
  terminated: "danger",
  rejected: "danger",
  error: "danger",
  weekend: "neutral",
  holiday: "neutral",
  inactive: "neutral",
  cancelled: "neutral",
  unpaid: "neutral",
};

export function statusTone(status: string): "ok" | "warn" | "danger" | "info" | "neutral" {
  return STATUS_TONE[String(status || "").toLowerCase()] ?? "neutral";
}

export function titleCase(value: string): string {
  return String(value)
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Days between two ISO dates, inclusive of both ends. */
export function daysBetween(start: string, end: string): number {
  const s = new Date(`${start}T00:00:00`);
  const e = new Date(`${end}T00:00:00`);
  if (Number.isNaN(s.getTime()) || Number.isNaN(e.getTime())) return 0;
  const diff = Math.round((e.getTime() - s.getTime()) / 86400000);
  return diff + 1;
}

/** Working days (Mon–Fri) between two ISO dates, inclusive. Holidays are applied server-side. */
export function previewWorkingDays(start: string, end: string): number | null {
  if (!start || !end || daysBetween(start, end) <= 0) return null;
  let count = 0;
  const s = new Date(`${start}T00:00:00`);
  const e = new Date(`${end}T00:00:00`);
  const cursor = new Date(s);
  while (cursor <= e) {
    const dow = cursor.getDay();
    if (dow !== 0 && dow !== 6) count += 1;
    cursor.setDate(cursor.getDate() + 1);
  }
  return count;
}
