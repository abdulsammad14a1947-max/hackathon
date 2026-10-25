"use client";

import Link from "next/link";
import { useApi } from "@/hooks/useApi";
import { asPage, asRows, pick, toNum, toStr, statusTone } from "@/lib/utils";
import { fmtDate, fmtHours, fmtMoney, fmtNumber, fmtTime } from "@/lib/format";
import type { Announcement, EmployeeAnalytics, Payslip } from "@/types/api";
import { Card } from "@/components/ui/Card";
import { ErrorState, EmptyState } from "@/components/ui/States";
import { StatsSkeleton, ListSkeleton, TableSkeleton } from "@/components/ui/Skeleton";
import { ProgressRow } from "@/components/ui/Chart";
import { Table, TH, TD, TR } from "@/components/ui/Table";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import {
  normaliseBalances,
  normaliseToday,
  normaliseWeekHours,
} from "./normalise";

export function EmployeeDashboard() {
  const { data, loading, error, reload, errorMessage } = useApi<EmployeeAnalytics>(
    "/api/analytics/employee/me",
  );

  if (error) {
    return <ErrorState message={errorMessage} onRetry={reload} />;
  }

  if (loading && !data) {
    return (
      <div className="space-y-6">
        <div>
          <h2 className="text-lg font-semibold text-text">My day</h2>
          <p className="mt-1 text-sm text-muted">Attendance, leave and pay at a glance.</p>
        </div>
        <StatsSkeleton count={4} />
        <div className="grid gap-4 lg:grid-cols-2">
          <ListSkeleton rows={3} />
          <TableSkeleton rows={4} cols={4} />
        </div>
      </div>
    );
  }

  const today = normaliseToday(data?.today_status);
  const week = normaliseWeekHours(data?.week_hours);
  const balances = normaliseBalances(data?.leave_balances);
  const recent = asRows(data?.recent_attendance)
    .map((r) => ({
      date: toStr(pick(r, ["date", "day"]), "—"),
      status: toStr(pick(r, ["status"]), "—"),
      check_in: toStr(pick(r, ["check_in", "in"]), ""),
      check_out: toStr(pick(r, ["check_out", "out"]), ""),
      worked_hours: toNum(pick(r, ["worked_hours", "hours"]), 0),
    }))
    .slice(0, 6);

  const payslipRow = data?.last_payslip;
  const payslip = isRecord(payslipRow) ? (payslipRow as unknown as Payslip) : null;

  const announcements = asPage<Announcement>(data?.announcements).items.slice(0, 4);

  const noData =
    !data ||
    (recent.length === 0 &&
      balances.length === 0 &&
      !payslip &&
      announcements.length === 0 &&
      today.status === "Not recorded");

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-text">My day</h2>
        <p className="mt-1 text-sm text-muted">
          {fmtDate(new Date().toISOString())} — attendance, leave and pay.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card
          title="Today's status"
          actions={<StatusBadge status={today.status} />}
          className="lg:col-span-1"
        >
          <dl className="space-y-3 text-sm">
            <div className="flex items-center justify-between">
              <dt className="text-muted">Check-in</dt>
              <dd className="font-medium tabular-nums text-text">{fmtTime(today.checkIn)}</dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-muted">Check-out</dt>
              <dd className="font-medium tabular-nums text-text">{fmtTime(today.checkOut)}</dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-muted">Late check-ins (this month)</dt>
              <dd className="font-medium tabular-nums text-text">
                {fmtNumber(data?.late_count)}
              </dd>
            </div>
          </dl>
          <Link href="/attendance" className="mt-4 block">
            <Button className="w-full">Open attendance</Button>
          </Link>
        </Card>

        <Card title="Weekly hours" description={`Target ${fmtHours(week.target)}`}>
          <p className="mb-3 text-3xl font-semibold tabular-nums text-text">
            {fmtHours(week.hours)}
          </p>
          <ProgressRow
            label="Progress"
            value={Number((week.hours ?? 0).toFixed(1))}
            max={week.target}
            tone={week.hours >= week.target ? "success" : "accent"}
          />
          <p className="mt-3 text-xs text-muted">
            {week.hours >= week.target
              ? "Weekly target reached."
              : `${fmtHours(Math.max(week.target - week.hours, 0))} to reach the weekly target.`}
          </p>
        </Card>

        <Card title="Leave balances" description="Remaining days by type">
          {balances.length === 0 ? (
            <EmptyState compact title="No balances configured" description="Leave types are added by your administrator." />
          ) : (
            <ul className="space-y-3">
              {balances.map((b) => (
                <li key={b.code} className="flex items-center justify-between gap-3 text-sm">
                  <span className="min-w-0">
                    <span className="block truncate font-medium text-text">{b.name}</span>
                    <span className="block text-xs text-muted">
                      {fmtNumber(b.used)} used
                      {b.pending > 0 ? ` · ${fmtNumber(b.pending)} pending` : ""}
                    </span>
                  </span>
                  <Badge tone={toNum(b.remaining) > 0 ? "ok" : "neutral"}>
                    {fmtNumber(b.remaining)} left
                  </Badge>
                </li>
              ))}
            </ul>
          )}
          <Link
            href="/leave"
            className="mt-4 inline-block text-xs font-medium text-accent hover:text-accent-hover"
          >
            Request leave →
          </Link>
        </Card>
      </div>

      {noData ? (
        <EmptyState
          title="Nothing recorded yet"
          description="Check in from the attendance page to start building your record."
          action={
            <Link
              href="/attendance"
              className="inline-flex rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-ink hover:bg-accent-hover"
            >
              Go to attendance
            </Link>
          }
        />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title="Recent attendance" description="My latest records">
            {recent.length === 0 ? (
              <EmptyState compact title="No attendance records yet" />
            ) : (
              <div className="overflow-hidden rounded-lg border border-border">
                <Table>
                  <thead>
                    <TR>
                      <TH>Date</TH>
                      <TH>Status</TH>
                      <TH align="right">In</TH>
                      <TH align="right">Out</TH>
                      <TH align="right">Hours</TH>
                    </TR>
                  </thead>
                  <tbody>
                    {recent.map((r) => (
                      <TR key={r.date}>
                        <TD className="tabular-nums text-muted">{fmtDate(r.date)}</TD>
                        <TD>
                          <Badge tone={statusTone(r.status)}>{r.status.replace(/_/g, " ")}</Badge>
                        </TD>
                        <TD align="right" className="tabular-nums">{fmtTime(r.check_in)}</TD>
                        <TD align="right" className="tabular-nums">{fmtTime(r.check_out)}</TD>
                        <TD align="right" className="tabular-nums">{fmtHours(r.worked_hours)}</TD>
                      </TR>
                    ))}
                  </tbody>
                </Table>
              </div>
            )}
          </Card>

          <div className="space-y-4">
            <Card
              title="Last payslip"
              actions={
                <Link href="/payslips" className="text-xs font-medium text-accent hover:text-accent-hover">
                  All payslips →
                </Link>
              }
            >
              {payslip ? (
                <div className="flex items-end justify-between gap-4">
                  <div>
                    <p className="text-sm text-muted">
                      {fmtDate(new Date(Number(payslip.period_year), Number(payslip.period_month) - 1, 1))}
                    </p>
                    <p className="mt-1 text-2xl font-semibold tabular-nums text-text">
                      {fmtMoney(payslip.net_pay)}
                    </p>
                    <p className="text-xs text-muted">Net pay</p>
                  </div>
                  <div className="text-right text-xs text-muted">
                    <p>Gross {fmtMoney(payslip.gross)}</p>
                    <p>Tax {fmtMoney(payslip.tax)}</p>
                  </div>
                </div>
              ) : (
                <EmptyState compact title="No payslip yet" description="Finalized payroll runs appear here." />
              )}
            </Card>

            <Card
              title="Announcements"
              actions={
                <Link
                  href="/announcements"
                  className="text-xs font-medium text-accent hover:text-accent-hover"
                >
                  All →
                </Link>
              }
            >
              {announcements.length === 0 ? (
                <EmptyState compact title="No announcements" />
              ) : (
                <ul className="divide-y divide-border">
                  {announcements.map((a) => (
                    <li key={a.id} className="py-3 first:pt-0 last:pb-0">
                      <p className="truncate text-sm font-medium text-text">{a.title}</p>
                      <p className="mt-0.5 line-clamp-2 text-xs text-muted">{a.body}</p>
                      <p className="mt-1 text-[11px] text-muted/70">{fmtDate(a.created_at)}</p>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}
