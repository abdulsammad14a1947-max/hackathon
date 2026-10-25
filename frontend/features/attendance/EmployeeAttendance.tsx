"use client";

import { useCallback, useMemo, useState } from "react";
import Link from "next/link";
import { api, ApiError, errorMessage } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { asPage, asRows, isObject, pick, toNum, toStr } from "@/lib/utils";
import { fmtDate, fmtHours, fmtTime, isoDay, monthName, todayISO } from "@/lib/format";
import type { Correction } from "@/types/api";
import { Card, StatCard } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Field, Input, Textarea } from "@/components/ui/Field";
import { ErrorState } from "@/components/ui/States";
import { StatsSkeleton } from "@/components/ui/Skeleton";
import { Icon } from "@/components/layout/Icon";
import { useToast } from "@/components/ui/Toast";
import { CorrectionsList } from "@/features/employees/EmployeeProfile";
import { cx } from "@/lib/utils";

const WEEK_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const STATUS_CLASS: Record<string, string> = {
  present: "bg-success/20 text-success border-success/40",
  late: "bg-warning/20 text-warning border-warning/40",
  half_day: "bg-warning/15 text-warning border-warning/30",
  missing_checkout: "bg-warning/15 text-warning border-warning/30",
  absent: "bg-danger/20 text-danger border-danger/40",
  on_leave: "bg-info/20 text-info border-info/40",
  weekend: "bg-surface-3 text-muted border-border",
  holiday: "bg-info/10 text-info border-info/30",
};

interface Coords {
  lat: number;
  lng: number;
  accuracy_m: number;
}

function geoErrorText(code: number): string {
  if (code === 1) return "Location permission was denied.";
  if (code === 2) return "Your location could not be determined.";
  if (code === 3) return "Location request timed out.";
  return "Location unavailable.";
}

export function EmployeeAttendance() {
  const toast = useToast();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [checkingIn, setCheckingIn] = useState(false);
  const [checkingOut, setCheckingOut] = useState(false);
  const [geoError, setGeoError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const { data, loading, error, reload, errorMessage: listError } = useApi<unknown>(
    `/api/attendance/me?year=${year}&month=${month}`,
  );
  const corrections = useApi<unknown>("/api/attendance/corrections");

  const records = useMemo(() => {
    if (!isObject(data)) return [];
    const list = asRows(data.records ?? data.items ?? data);
    return list
      .filter((r) => toStr(pick(r, ["date", "day"]), ""))
      .map((r) => ({
        date: toStr(pick(r, ["date", "day"]), ""),
        status: toStr(pick(r, ["status"]), ""),
        check_in: toStr(pick(r, ["check_in", "in"]), ""),
        check_out: toStr(pick(r, ["check_out", "out"]), ""),
        worked_hours: toNum(pick(r, ["worked_hours", "hours"]), 0),
        source: toStr(pick(r, ["source"]), "manual"),
      }));
  }, [data]);

  const summary = useMemo(
    () => (isObject(data) && isObject(data.summary) ? (data.summary as Record<string, number>) : {}),
    [data],
  );

  const today = records.find((r) => r.date === todayISO());
  const checkedIn = Boolean(today?.check_in);
  const checkedOut = Boolean(today?.check_out);

  const getLocation = useCallback(
    () =>
      new Promise<Coords | null>((resolve) => {
        if (typeof navigator === "undefined" || !("geolocation" in navigator)) {
          setGeoError("This browser does not support geolocation.");
          resolve(null);
          return;
        }
        navigator.geolocation.getCurrentPosition(
          (pos) =>
            resolve({
              lat: pos.coords.latitude,
              lng: pos.coords.longitude,
              accuracy_m: Math.round(pos.coords.accuracy ?? 0),
            }),
          (err) => {
            setGeoError(geoErrorText(err.code));
            resolve(null);
          },
          { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 },
        );
      }),
    [],
  );

  const checkIn = async (withLocation: boolean) => {
    setCheckingIn(true);
    setActionError(null);
    setGeoError(null);
    let coords: Coords | null = null;
    if (withLocation) {
      coords = await getLocation();
      if (!coords) {
        setCheckingIn(false);
        return;
      }
    }
    try {
      await api("/api/attendance/check-in", {
        method: "POST",
        body: coords
          ? { lat: coords.lat, lng: coords.lng, accuracy_m: coords.accuracy_m }
          : {},
      });
      toast({ type: "success", message: "Checked in successfully." });
      reload();
    } catch (err) {
      const msg = errorMessage(err);
      setActionError(msg);
      if (!(err instanceof ApiError) || err.status !== 403) {
        toast({ type: "error", message: msg });
      }
    } finally {
      setCheckingIn(false);
    }
  };

  const checkOut = async () => {
    setCheckingOut(true);
    setActionError(null);
    try {
      await api("/api/attendance/check-out", { method: "POST", body: {} });
      toast({ type: "success", message: "Checked out successfully." });
      reload();
    } catch (err) {
      const msg = errorMessage(err);
      setActionError(msg);
      toast({ type: "error", message: msg });
    } finally {
      setCheckingOut(false);
    }
  };

  const shiftMonth = (delta: number) => {
    const next = new Date(year, month - 1 + delta, 1);
    setYear(next.getFullYear());
    setMonth(next.getMonth() + 1);
  };

  return (
    <div className="space-y-6">
      {/* Action card */}
      <Card
        title="Today"
        description={fmtDate(todayISO())}
        actions={
          <Badge tone={checkedIn ? (checkedOut ? "ok" : "info") : "neutral"}>
            {checkedIn ? (checkedOut ? "Day complete" : "Checked in") : "Not checked in"}
          </Badge>
        }
      >
        <div className="grid gap-5 lg:grid-cols-[320px,1fr]">
          <div className="space-y-3">
            <div className="flex gap-3">
              <Button
                className="flex-1"
                size="lg"
                onClick={() => checkIn(true)}
                disabled={checkedIn}
                loading={checkingIn}
              >
                <Icon name="check" className="h-5 w-5" /> Check in
              </Button>
              <Button
                className="flex-1"
                size="lg"
                variant="secondary"
                onClick={checkOut}
                disabled={!checkedIn || checkedOut}
                loading={checkingOut}
              >
                <Icon name="logout" className="h-5 w-5" /> Check out
              </Button>
            </div>

            <Link
              href="/camera"
              className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-border bg-surface-2 px-4 py-2 text-sm text-text transition-[background-color,border-color,transform] duration-200 ease-snappy hover:-translate-y-px hover:border-border-strong hover:bg-surface-3 active:translate-y-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-bg"
            >
              <Icon name="camera" className="h-4 w-4" /> Camera check-in
            </Link>

            {!checkedIn && !checkingIn && geoError && (
              <div className="rounded-lg border border-warning/40 bg-warning/10 p-3 text-xs text-warning">
                <p>{geoError}</p>
                <p className="mt-1 text-muted">
                  You can still check in without location — the server decides whether coordinates
                  are required.
                </p>
                <Button
                  size="sm"
                  variant="secondary"
                  className="mt-2"
                  onClick={() => checkIn(false)}
                >
                  Check in without location
                </Button>
              </div>
            )}

            {actionError && (
              <div role="alert" className="rounded-lg border border-danger/40 bg-danger/10 p-3 text-sm text-danger">
                {actionError}
              </div>
            )}

            <dl className="rounded-lg border border-border bg-surface-2 p-4 text-sm">
              <div className="flex justify-between py-1">
                <dt className="text-muted">Check-in</dt>
                <dd className="tabular-nums">{fmtTime(today?.check_in)}</dd>
              </div>
              <div className="flex justify-between py-1">
                <dt className="text-muted">Check-out</dt>
                <dd className="tabular-nums">{fmtTime(today?.check_out)}</dd>
              </div>
              <div className="flex justify-between py-1">
                <dt className="text-muted">Worked</dt>
                <dd className="tabular-nums">{fmtHours(today?.worked_hours)}</dd>
              </div>
              <div className="flex justify-between py-1">
                <dt className="text-muted">Method</dt>
                <dd>{today ? (today.source === "face_camera" ? "Camera" : "Manual") : "—"}</dd>
              </div>
            </dl>
          </div>

          <div>
            {loading && !data && <StatsSkeleton count={4} />}
            {error && !loading && <ErrorState message={listError} onRetry={reload} />}
            {!loading && data !== undefined && (
              <>
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  {Object.entries(summary).length > 0 ? (
                    Object.entries(summary).map(([key, value]) => (
                      <StatCard key={key} label={key.replace(/_/g, " ")} value={String(value)} />
                    ))
                  ) : (
                    <p className="col-span-4 text-sm text-muted">
                      No summary available for this month yet.
                    </p>
                  )}
                </div>

                {/* Month calendar */}
                <div className="mt-5 flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-text">
                    {monthName(month)} {year} — daily status
                  </h3>
                  <div className="flex gap-1">
                    <Button size="sm" variant="secondary" onClick={() => shiftMonth(-1)} aria-label="Previous month">
                      ←
                    </Button>
                    <Button size="sm" variant="secondary" onClick={() => shiftMonth(1)} aria-label="Next month">
                      →
                    </Button>
                  </div>
                </div>

                <MonthCalendar year={year} month={month} records={records} />
              </>
            )}
          </div>
        </div>
      </Card>

      {/* Corrections */}
      <div className="grid gap-4 lg:grid-cols-2">
        <CorrectionForm onSubmitted={() => { reload(); corrections.reload(); }} />
        <Card title="My correction requests" description="Submitted to HR for review">
          {corrections.error ? (
            <ErrorState message={corrections.errorMessage} onRetry={corrections.reload} />
          ) : (
            <CorrectionsList
              corrections={asPage<Correction>(corrections.data).items}
              loading={corrections.loading}
            />
          )}
        </Card>
      </div>
    </div>
  );
}

function MonthCalendar({
  year,
  month,
  records,
}: {
  year: number;
  month: number;
  records: { date: string; status: string }[];
}) {
  const byDate = new Map(records.map((r) => [r.date, r.status]));
  const first = new Date(year, month - 1, 1);
  const daysInMonth = new Date(year, month, 0).getDate();
  // Monday-first offset
  const offset = (first.getDay() + 6) % 7;
  const cells: (number | null)[] = [
    ...Array.from({ length: offset }, () => null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];

  const today = todayISO();

  return (
    <div className="mt-3">
      <div className="grid grid-cols-7 gap-1.5 text-center text-[11px] font-medium text-muted">
        {WEEK_LABELS.map((d) => (
          <div key={d} className="py-1">
            {d}
          </div>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-1.5">
        {cells.map((day, i) => {
          if (day === null) return <div key={`e-${i}`} />;
          const iso = isoDay(new Date(year, month - 1, day));
          const status = byDate.get(iso);
          const weekend = i % 7 >= 5;
          const cls = status
            ? (STATUS_CLASS[status] ?? "bg-surface-3 text-text border-border")
            : weekend
              ? "bg-surface-3/60 text-muted border-border"
              : "bg-surface-2 text-muted/70 border-border";
          return (
            <div
              key={iso}
              title={status ? `${fmtDate(iso)} — ${status.replace(/_/g, " ")}` : fmtDate(iso)}
              className={cx(
                "flex h-11 flex-col items-center justify-center rounded-lg border text-xs transition-colors",
                cls,
                iso === today && "ring-1 ring-accent",
              )}
            >
              <span className="font-medium">{day}</span>
            </div>
          );
        })}
      </div>
      <ul className="mt-4 flex flex-wrap gap-x-4 gap-y-2 text-[11px] text-muted">
        {[
          ["present", "Present"],
          ["late", "Late"],
          ["half_day", "Half day"],
          ["absent", "Absent"],
          ["on_leave", "On leave"],
          ["weekend", "Weekend"],
          ["holiday", "Holiday"],
          ["missing_checkout", "Missing checkout"],
        ].map(([key, label]) => (
          <li key={key} className="flex items-center gap-1.5">
            <span className={cx("h-2.5 w-2.5 rounded-sm border", STATUS_CLASS[key])} />
            {label}
          </li>
        ))}
        <li className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm border bg-surface-2 border-border" /> No record
        </li>
      </ul>
    </div>
  );
}

function CorrectionForm({ onSubmitted }: { onSubmitted: () => void }) {
  const toast = useToast();
  const [date, setDate] = useState(todayISO());
  const [checkIn, setCheckIn] = useState("09:00");
  const [checkOut, setCheckOut] = useState("17:00");
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setErrors({});
    setFormError(null);
    try {
      await api("/api/attendance/corrections", {
        method: "POST",
        body: {
          attendance_date: date,
          requested_check_in: checkIn,
          requested_check_out: checkOut,
          reason: reason.trim(),
        },
      });
      toast({ type: "success", message: "Correction request submitted." });
      setReason("");
      onSubmitted();
    } catch (err) {
      if (err instanceof ApiError) {
        setErrors(err.fieldErrors);
        setFormError(err.message);
      } else {
        setFormError(errorMessage(err));
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card title="Request an attendance correction" description="HR reviews every request.">
      <form onSubmit={submit} className="space-y-4" noValidate>
        {formError && (
          <div role="alert" className="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger">
            {formError}
          </div>
        )}
        <Field label="Attendance date" htmlFor="corr_date" error={errors.attendance_date} required>
          <Input id="corr_date" type="date" value={date} onChange={(e) => setDate(e.target.value)} required />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Correct check-in" htmlFor="corr_in" error={errors.requested_check_in} required>
            <Input id="corr_in" type="time" value={checkIn} onChange={(e) => setCheckIn(e.target.value)} required />
          </Field>
          <Field label="Correct check-out" htmlFor="corr_out" error={errors.requested_check_out} required>
            <Input id="corr_out" type="time" value={checkOut} onChange={(e) => setCheckOut(e.target.value)} required />
          </Field>
        </div>
        <Field label="Reason" htmlFor="corr_reason" error={errors.reason} required>
          <Textarea
            id="corr_reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Forgot to check out — was in a client meeting."
            required
          />
        </Field>
        <Button type="submit" loading={saving}>
          Submit request
        </Button>
      </form>
    </Card>
  );
}
