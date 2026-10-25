import { cx } from "@/lib/utils";

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cx("animate-pulse rounded bg-surface-3", className)} />;
}

export function CardSkeleton({ className }: { className?: string }) {
  return (
    <div
      className={cx(
        "rounded-xl border border-border bg-surface p-5 shadow-[var(--shadow-card)]",
        className,
      )}
      aria-hidden
    >
      <Skeleton className="h-3 w-28" />
      <Skeleton className="mt-4 h-7 w-32" />
      <Skeleton className="mt-3 h-3 w-40" />
    </div>
  );
}

export function StatsSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {Array.from({ length: count }).map((_, i) => (
        <CardSkeleton key={i} />
      ))}
    </div>
  );
}

export function ChartSkeleton({ className }: { className?: string }) {
  return (
    <div
      className={cx("flex h-64 items-end gap-3 rounded-lg bg-surface-2 p-4", className)}
      aria-hidden
    >
      {[45, 70, 35, 85, 55, 65, 40].map((h, i) => (
        <div key={i} className="flex-1 animate-pulse rounded-t bg-surface-3" style={{ height: `${h}%` }} />
      ))}
    </div>
  );
}

export function TableSkeleton({ rows = 6, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-surface" aria-hidden>
      <div className="flex gap-4 border-b border-border bg-surface-2 px-4 py-3">
        {Array.from({ length: cols }).map((_, i) => (
          <Skeleton key={i} className="h-3 flex-1" />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex gap-4 border-b border-border px-4 py-3 last:border-b-0">
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton key={c} className="h-3 flex-1" />
          ))}
        </div>
      ))}
    </div>
  );
}

export function ListSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-3" aria-hidden>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="rounded-lg border border-border bg-surface-2 p-4">
          <Skeleton className="h-3 w-1/3" />
          <Skeleton className="mt-2 h-3 w-2/3" />
        </div>
      ))}
    </div>
  );
}

export function PageSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-8 w-56" />
      <StatsSkeleton />
      <div className="grid gap-4 lg:grid-cols-2">
        <Skeleton className="h-72 rounded-xl bg-surface" />
        <Skeleton className="h-72 rounded-xl bg-surface" />
      </div>
    </div>
  );
}
