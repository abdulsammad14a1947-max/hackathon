"use client";

import Link from "next/link";
import { useApi } from "@/hooks/useApi";
import { asBullets, asPairs, asRows, pick, toNum, toStr } from "@/lib/utils";
import { fmtNumber, monthName } from "@/lib/format";
import type { HrAnalytics } from "@/types/api";
import { Card, StatCard } from "@/components/ui/Card";
import { ErrorState, EmptyState } from "@/components/ui/States";
import { StatsSkeleton, ChartSkeleton, TableSkeleton } from "@/components/ui/Skeleton";
import { BarPairChart, LineTrendChart, ProgressRow } from "@/components/ui/Chart";
import { Table, TH, TD, TR } from "@/components/ui/Table";
import { Badge } from "@/components/ui/Badge";
import { normaliseTrend } from "./normalise";

export function HrDashboard() {
  const { data, loading, error, reload, errorMessage } = useApi<HrAnalytics>("/api/analytics/hr");

  if (error) {
    return <ErrorState message={errorMessage} onRetry={reload} />;
  }

  if (loading && !data) {
    return (
      <div className="space-y-6">
        <div>
          <h2 className="text-lg font-semibold text-text">Today at a glance</h2>
          <p className="mt-1 text-sm text-muted">Live attendance and approval workload.</p>
        </div>
        <StatsSkeleton count={5} />
        <div className="grid gap-4 lg:grid-cols-2">
          <ChartSkeleton />
          <ChartSkeleton />
        </div>
        <TableSkeleton rows={5} cols={4} />
      </div>
    );
  }

  const trend = normaliseTrend(data?.attendance_trend);
  const absenteeism = asPairs(data?.absenteeism_by_department);
  const utilization = asRows(data?.leave_utilization).length
    ? asRows(data?.leave_utilization).map((r) => ({
        label: toStr(pick(r, ["name", "code", "leave_type"]), "—"),
        used: toNum(pick(r, ["used", "taken", "approved"]), 0),
        quota: toNum(pick(r, ["quota", "yearly_quota", "total"]), 0),
      }))
    : Object.entries(
        (data?.leave_utilization && typeof data.leave_utilization === "object"
          ? (data.leave_utilization as Record<string, unknown>)
          : {}) ?? {},
      ).map(([key, raw]) => ({
        label: key,
        used: toNum(isRecord(raw) ? raw.used : raw, 0),
        quota: toNum(isRecord(raw) ? raw.quota ?? raw.total : undefined, 0),
      }));

  const lateRows = asPairs(data?.top_late_comers, ["name", "employee_name", "full_name", "employee_code"], ["late_count", "count", "value", "late"]);
  const insights = asBullets(data?.insights);

  const pending = toNum(data?.pending_approvals);
  const noData =
    !data ||
    (toNum(data.headcount) === 0 &&
      trend.length === 0 &&
      absenteeism.length === 0 &&
      lateRows.length === 0 &&
      insights.length === 0);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-text">Today at a glance</h2>
          <p className="mt-1 text-sm text-muted">
            {monthName(new Date().getMonth() + 1)} {new Date().getFullYear()} — attendance,
            approvals and leave.
          </p>
        </div>
        <div className="flex gap-2">
          <Link
            href="/attendance"
            className="rounded-lg border border-border bg-surface-2 px-3 py-1.5 text-xs font-medium text-text hover:border-border-strong"
          >
            Day board
          </Link>
          <Link
            href="/leave"
            className="rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-accent-ink hover:bg-accent-hover"
          >
            Approvals {pending > 0 ? `(${pending})` : ""}
          </Link>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <StatCard label="Headcount" value={fmtNumber(data?.headcount)} loading={loading} />
        <StatCard
          label="Present"
          value={fmtNumber(data?.present)}
          tone="ok"
          hint="Checked in today"
          loading={loading}
        />
        <StatCard label="Late" value={fmtNumber(data?.late)} tone="warn" loading={loading} />
        <StatCard
          label="On leave"
          value={fmtNumber(data?.on_leave)}
          tone="info"
          loading={loading}
        />
        <StatCard
          label="Pending approvals"
          value={fmtNumber(data?.pending_approvals)}
          tone={pending > 0 ? "warn" : undefined}
          loading={loading}
        />
      </div>

      {noData ? (
        <EmptyState
          title="No attendance data for today"
          description="Records appear as soon as employees check in or leave requests are submitted."
          action={
            <Link
              href="/attendance"
              className="inline-flex rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-ink hover:bg-accent-hover"
            >
              Open attendance board
            </Link>
          }
        />
      ) : (
        <>
          <div className="grid gap-4 lg:grid-cols-2">
            <LineTrendChart
              title="Attendance trend"
              description="Present per day, last 14 days"
              data={trend}
            />
            <BarPairChart
              title="Absenteeism by department"
              description="Absent records in the current period"
              data={absenteeism}
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="Leave utilization" description="Approved days against quota">
              {utilization.length === 0 ? (
                <EmptyState compact title="No leave taken yet" />
              ) : (
                <div className="space-y-4">
                  {utilization.map((row) => (
                    <ProgressRow
                      key={row.label}
                      label={row.label}
                      value={row.used}
                      max={row.quota}
                      hint={row.quota > 0 ? "days" : "unlimited"}
                      tone={row.quota > 0 && row.used / row.quota > 0.8 ? "warning" : "accent"}
                    />
                  ))}
                </div>
              )}
            </Card>

            <Card title="Top late comers" description="Employees with the most late check-ins">
              {lateRows.length === 0 ? (
                <EmptyState compact title="No late arrivals recorded" />
              ) : (
                <TableContainerInline>
                  <Table>
                    <thead>
                      <TR>
                        <TH>Employee</TH>
                        <TH align="right">Late arrivals</TH>
                      </TR>
                    </thead>
                    <tbody>
                      {lateRows.slice(0, 5).map((row, i) => (
                        <TR key={`${row.label}-${i}`}>
                          <TD>
                            <span className="flex items-center gap-2">
                              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-surface-3 text-[10px] font-semibold text-muted">
                                {i + 1}
                              </span>
                              {row.label}
                            </span>
                          </TD>
                          <TD align="right">
                            <Badge tone={row.value >= 3 ? "warn" : "neutral"}>
                              {row.value}
                            </Badge>
                          </TD>
                        </TR>
                      ))}
                    </tbody>
                  </Table>
                </TableContainerInline>
              )}
            </Card>
          </div>

          <Card title="Insights" description="Generated server-side from your people data">
            {insights.length === 0 ? (
              <EmptyState compact title="Not enough data for insights yet" />
            ) : (
              <ul className="space-y-3">
                {insights.map((text, i) => (
                  <li key={i} className="flex items-start gap-3 text-sm text-text/90">
                    <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-accent/15 text-[11px] font-semibold text-accent">
                      {i + 1}
                    </span>
                    <span className="leading-relaxed">{text}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </>
      )}
    </div>
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function TableContainerInline({ children }: { children: React.ReactNode }) {
  return <div className="overflow-hidden rounded-lg border border-border">{children}</div>;
}
