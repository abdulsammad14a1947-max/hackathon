"use client";

import Link from "next/link";
import { useApi } from "@/hooks/useApi";
import { asPairs, isObject, toNum } from "@/lib/utils";
import { fmtDateTime, fmtMoney, fmtNumber } from "@/lib/format";
import type { AdminAnalytics } from "@/types/api";
import { Card, StatCard } from "@/components/ui/Card";
import { ErrorState, EmptyState } from "@/components/ui/States";
import { StatsSkeleton, ChartSkeleton, ListSkeleton } from "@/components/ui/Skeleton";
import { BarPairChart, DonutChart } from "@/components/ui/Chart";
import { Badge } from "@/components/ui/Badge";
import {
  normaliseRecentAudit,
} from "./normalise";

export function AdminDashboard() {
  const { data, loading, error, reload, errorMessage } = useApi<AdminAnalytics>(
    "/api/analytics/admin",
  );

  if (error) {
    return <ErrorState message={errorMessage} onRetry={reload} />;
  }

  if (loading && !data) {
    return (
      <div className="space-y-6">
        <div>
          <h2 className="text-lg font-semibold text-text">Company overview</h2>
          <p className="mt-1 text-sm text-muted">Server-computed analytics for your tenant.</p>
        </div>
        <StatsSkeleton count={4} />
        <div className="grid gap-4 lg:grid-cols-2">
          <ChartSkeleton />
          <ChartSkeleton />
        </div>
        <div className="grid gap-4 lg:grid-cols-3">
          <ChartSkeleton className="h-64" />
          <ChartSkeleton className="h-64" />
          <div className="space-y-3">
            <ListSkeleton rows={3} />
          </div>
        </div>
      </div>
    );
  }

  const headcountByDept = asPairs(data?.headcount_by_department);
  const payrollByDept = asPairs(data?.payroll_cost_by_department);
  const gender = asPairs(data?.gender_breakdown, ["gender", "label", "name", "key"]);
  const tenureIsObject = isObject(data?.tenure);
  const tenurePairs = tenureIsObject || Array.isArray(data?.tenure) ? asPairs(data?.tenure) : [];
  const recentAudit = normaliseRecentAudit(data?.recent_audit);
  const avgTenure = !tenurePairs.length && data?.tenure !== undefined && !Array.isArray(data?.tenure)
    ? toNum(data?.tenure, Number.NaN)
    : Number.NaN;

  const noData =
    !data ||
    (toNum(data.headcount) === 0 &&
      headcountByDept.length === 0 &&
      payrollByDept.length === 0 &&
      recentAudit.length === 0);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-text">Company overview</h2>
          <p className="mt-1 text-sm text-muted">
            Headcount, payroll and audit activity computed by the API.
          </p>
        </div>
        {loading && <Badge tone="accent">Refreshing…</Badge>}
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Headcount" value={fmtNumber(data?.headcount)} hint="Active employees" />
        <StatCard
          label="Attrition YTD"
          value={fmtNumber(data?.attrition_ytd)}
          hint="Exits since 1 January"
          tone="warn"
        />
        <StatCard label="Payroll cost" value={fmtMoney(data?.payroll_cost)} hint="Current period" tone="info" />
        <StatCard label="Average salary" value={fmtMoney(data?.avg_salary)} hint="Annualised basic" />
      </div>

      {noData ? (
        <EmptyState
          title="No analytics data yet"
          description="Add employees and generate a payroll run — the company metrics will appear here automatically."
          action={
            <Link
              href="/employees"
              className="inline-flex rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-ink hover:bg-accent-hover"
            >
              Go to Employees
            </Link>
          }
        />
      ) : (
        <>
          <div className="grid gap-4 lg:grid-cols-2">
            <BarPairChart
              title="Headcount by department"
              description="Employees per department"
              data={headcountByDept}
            />
            <BarPairChart
              title="Payroll cost by department"
              description="Total cost for the current period"
              data={payrollByDept}
              format={(n) => fmtMoney(n)}
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <DonutChart title="Gender breakdown" data={gender} height={240} />
            <BarPairChart
              title="Tenure distribution"
              description={
                Number.isNaN(avgTenure) ? "Employees by tenure bucket" : undefined
              }
              data={tenurePairs}
              height={240}
            />
            <Card title="Recent activity" description="Latest audit log entries">
              {recentAudit.length === 0 ? (
                <EmptyState
                  compact
                  title="No audit entries yet"
                  description="Sign-ins, changes and approvals are recorded here."
                />
              ) : (
                <ul className="space-y-3">
                  {recentAudit.slice(0, 6).map((row, i) => (
                    <li key={`${row.action}-${i}`} className="flex items-start gap-3 text-sm">
                      <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                      <span className="min-w-0">
                        <span className="block truncate font-medium text-text">{row.action}</span>
                        <span className="block truncate text-xs text-muted">
                          {row.entity} · {row.actor}
                        </span>
                        <span className="block text-[11px] text-muted/70">
                          {fmtDateTime(row.at)}
                        </span>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              <Link
                href="/audit"
                className="mt-4 inline-block text-xs font-medium text-accent hover:text-accent-hover"
              >
                Open full audit log →
              </Link>
            </Card>
          </div>

          {!Number.isNaN(avgTenure) && (
            <Card title="Average tenure">
              <p className="text-2xl font-semibold tabular-nums text-text">
                {fmtNumber(avgTenure, " yrs")}
              </p>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
