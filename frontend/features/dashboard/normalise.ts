"use client";

import type { Pair } from "@/lib/utils";
import { asPairs, asRows, isObject, pick, toNum, toStr } from "@/lib/utils";

/** `[{date,present}]`, `[{label,value}]`, `{key: n}` or `[n, n, n]` → chart pairs. */
export function normaliseTrend(value: unknown): Pair[] {
  if (Array.isArray(value) && value.length > 0 && value.every((v) => typeof v === "number")) {
    const numbers = value as number[];
    const today = new Date();
    return numbers.map((n, i) => {
      const d = new Date(today);
      d.setDate(today.getDate() - (numbers.length - 1 - i));
      return { label: `${d.getDate()}/${d.getMonth() + 1}`, value: n };
    });
  }
  return asPairs(value, ["date", "label", "day", "name"], ["present", "value", "count", "total", "late"]);
}

interface TodayStatus {
  status: string;
  checkIn?: string;
  checkOut?: string;
  date?: string;
}

export function normaliseToday(value: unknown): TodayStatus {
  if (typeof value === "string") return { status: value };
  if (isObject(value)) {
    return {
      status: toStr(pick(value, ["status", "state", "label"]), "Not recorded"),
      checkIn: toStr(pick(value, ["check_in", "checkIn", "in"]), ""),
      checkOut: toStr(pick(value, ["check_out", "checkOut", "out"]), ""),
      date: toStr(pick(value, ["date", "day"]), ""),
    };
  }
  return { status: "Not recorded" };
}

export function normaliseWeekHours(value: unknown): { hours: number; target: number } {
  if (typeof value === "number" || typeof value === "string") {
    return { hours: toNum(value), target: 40 };
  }
  if (isObject(value)) {
    return {
      hours: toNum(pick(value, ["hours", "worked", "value", "week_hours"])),
      target: toNum(pick(value, ["target", "expected", "required"]), 40),
    };
  }
  return { hours: 0, target: 40 };
}

export interface BalanceRow {
  code: string;
  name: string;
  quota: number;
  used: number;
  pending: number;
  remaining: number;
}

export function normaliseBalances(value: unknown): BalanceRow[] {
  const rows = asRows(value);
  if (rows.length) {
    return rows.map((r, i) => ({
      code: toStr(pick(r, ["code", "type", "leave_type"]), `T${i}`),
      name: toStr(pick(r, ["name", "label", "leave_type_name"]), `Type ${i + 1}`),
      quota: toNum(pick(r, ["quota", "yearly_quota", "total"]), -1),
      used: toNum(pick(r, ["used", "taken", "approved"]), 0),
      pending: toNum(pick(r, ["pending", "requests"]), 0),
      remaining: toNum(pick(r, ["remaining", "left", "balance"]), 0),
    }));
  }
  if (isObject(value)) {
    return Object.entries(value).map(([key, raw]) => {
      if (isObject(raw)) {
        return {
          code: key,
          name: toStr(pick(raw, ["name", "label"]), key),
          quota: toNum(pick(raw, ["quota", "yearly_quota", "total"]), -1),
          used: toNum(pick(raw, ["used", "taken"]), 0),
          pending: toNum(pick(raw, ["pending"]), 0),
          remaining: toNum(pick(raw, ["remaining", "left", "balance"]), 0),
        };
      }
      return { code: key, name: key, quota: -1, used: 0, pending: 0, remaining: toNum(raw) };
    });
  }
  return [];
}

export interface AuditRow {
  action: string;
  actor: string;
  entity: string;
  at?: string;
}

export function normaliseRecentAudit(value: unknown): AuditRow[] {
  return asRows(value).map((r) => ({
    action: toStr(pick(r, ["action", "event"]), "—"),
    actor: toStr(pick(r, ["actor_email", "actor", "email", "user"]), "—"),
    entity: toStr(pick(r, ["entity_type", "entity"]), "—"),
    at: toStr(pick(r, ["created_at", "timestamp", "at"]), ""),
  }));
}
