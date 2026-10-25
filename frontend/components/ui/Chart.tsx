"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card } from "./Card";
import { EmptyState } from "./States";
import { cx } from "@/lib/utils";

export const CHART_COLORS = [
  "#E7B75A", // brass — the brand series always goes first
  "#60A5FA",
  "#34D399",
  "#FB923C",
  "#A78BFA",
  "#2DD4BF",
  "#F472B6",
  "#F87171",
];

const AXIS_TICK = { fill: "#9A9DA6", fontSize: 11 } as const;

const TOOLTIP_STYLE = {
  backgroundColor: "#171A21",
  border: "1px solid #333944",
  borderRadius: 8,
  color: "#F2F1EE",
  fontSize: 12,
} as const;

export interface ChartPair {
  label: string;
  value: number;
}

function ChartFrame({
  title,
  description,
  empty,
  emptyDescription,
  height = 260,
  children,
}: {
  title: string;
  description?: string;
  empty?: boolean;
  emptyDescription?: string;
  height?: number;
  children: React.ReactNode;
}) {
  return (
    <Card title={title} description={description} bodyClassName="p-4">
      {empty ? (
        <div className="flex items-center justify-center" style={{ height }}>
          <EmptyState
            compact
            title="No data yet"
            description={emptyDescription ?? "Once records exist they will appear here."}
          />
        </div>
      ) : (
        <div style={{ height, width: "100%" }}>{children}</div>
      )}
    </Card>
  );
}

export function BarPairChart({
  title,
  description,
  data,
  format = (n) => String(n),
  height = 260,
}: {
  title: string;
  description?: string;
  data: ChartPair[];
  format?: (n: number) => string;
  height?: number;
}) {
  const empty = data.length === 0 || data.every((d) => d.value === 0);
  return (
    <ChartFrame title={title} description={description} empty={empty} height={height}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="#23272F" strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="label" tick={AXIS_TICK} axisLine={{ stroke: "#23272F" }} tickLine={false} interval={0} angle={data.length > 6 ? -25 : 0} textAnchor={data.length > 6 ? "end" : "middle"} height={data.length > 6 ? 60 : 30} />
          <YAxis tick={AXIS_TICK} axisLine={false} tickLine={false} width={44} />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            cursor={{ fill: "rgba(231,183,90,0.10)" }}
            formatter={(value) => [format(Number(value ?? 0)), title]}
          />
          <Bar dataKey="value" radius={[4, 4, 0, 0]}>
            {data.map((entry, i) => (
              <Cell key={entry.label + i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

export function LineTrendChart({
  title,
  description,
  data,
  format = (n) => String(n),
  height = 260,
}: {
  title: string;
  description?: string;
  data: ChartPair[];
  format?: (n: number) => string;
  height?: number;
}) {
  const empty = data.length === 0;
  return (
    <ChartFrame title={title} description={description} empty={empty} height={height}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="#23272F" strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="label" tick={AXIS_TICK} axisLine={{ stroke: "#23272F" }} tickLine={false} minTickGap={16} />
          <YAxis tick={AXIS_TICK} axisLine={false} tickLine={false} width={44} allowDecimals={false} />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            cursor={{ stroke: "#E7B75A", strokeDasharray: "4 4" }}
            formatter={(value) => [format(Number(value ?? 0)), title]}
          />
          <Line
            type="monotone"
            dataKey="value"
            stroke="#E7B75A"
            strokeWidth={2}
            dot={{ r: 3, fill: "#E7B75A", strokeWidth: 0 }}
            activeDot={{ r: 5 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

export function DonutChart({
  title,
  description,
  data,
  height = 260,
}: {
  title: string;
  description?: string;
  data: ChartPair[];
  height?: number;
}) {
  const empty = data.length === 0 || data.every((d) => d.value === 0);
  return (
    <ChartFrame title={title} description={description} empty={empty} height={height}>
      <div className="flex h-full items-center gap-4">
        <div className="h-full min-w-0 flex-1">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data}
                dataKey="value"
                nameKey="label"
                innerRadius="55%"
                outerRadius="85%"
                paddingAngle={2}
                stroke="#111318"
              >
                {data.map((entry, i) => (
                  <Cell key={entry.label + i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip contentStyle={TOOLTIP_STYLE} />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <ul className="w-32 shrink-0 space-y-1.5 text-xs">
          {data.map((entry, i) => (
            <li key={entry.label + i} className="flex items-center justify-between gap-2">
              <span className="flex min-w-0 items-center gap-1.5">
                <span
                  className="h-2.5 w-2.5 shrink-0 rounded-sm"
                  style={{ background: CHART_COLORS[i % CHART_COLORS.length] }}
                />
                <span className="truncate text-muted">{entry.label}</span>
              </span>
              <span className="font-medium tabular-nums text-text">{entry.value}</span>
            </li>
          ))}
        </ul>
      </div>
    </ChartFrame>
  );
}

/** Horizontal progress row used for leave utilization / weekly hours. */
export function ProgressRow({
  label,
  value,
  max,
  hint,
  tone = "accent",
}: {
  label: string;
  value: number;
  max: number;
  hint?: string;
  tone?: "accent" | "success" | "warning" | "danger";
}) {
  const pct = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0;
  const bar =
    tone === "success"
      ? "bg-success"
      : tone === "warning"
        ? "bg-warning"
        : tone === "danger"
          ? "bg-danger"
          : "bg-accent";
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 text-xs">
        <span className="truncate font-medium text-text">{label}</span>
        <span className="shrink-0 tabular-nums text-muted">
          {value}
          {max > 0 ? ` / ${max}` : ""} {hint && <span className="text-muted/70">{hint}</span>}
        </span>
      </div>
      <div className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-surface-3">
        <div
          className={cx("h-full rounded-full transition-all", bar)}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
