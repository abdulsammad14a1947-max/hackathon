import { cx } from "@/lib/utils";

export function Card({
  title,
  description,
  actions,
  children,
  className,
  bodyClassName,
}: {
  title?: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section
      className={cx(
        "rounded-xl border border-border bg-surface shadow-[var(--shadow-card)]",
        "transition-[border-color,box-shadow] duration-300 ease-snappy hover:border-border-strong",
        className,
      )}
    >
      {(title || actions) && (
        <header className="flex flex-wrap items-start justify-between gap-3 border-b border-border px-5 py-4">
          <div>
            {title && <h2 className="text-sm font-semibold text-text">{title}</h2>}
            {description && <p className="mt-1 text-xs text-muted">{description}</p>}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={cx("p-5", bodyClassName)}>{children}</div>
    </section>
  );
}

export function StatCard({
  label,
  value,
  hint,
  tone,
  loading,
}: {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  tone?: "ok" | "warn" | "danger" | "info";
  loading?: boolean;
}) {
  const toneClass =
    tone === "ok"
      ? "text-success"
      : tone === "warn"
        ? "text-warning"
        : tone === "danger"
          ? "text-danger"
          : tone === "info"
            ? "text-info"
            : "text-text";
  return (
    /* Double-bezel: hairline outer shell, recessed inner core. */
    <div className="rounded-xl border border-border/80 bg-surface/60 p-1 shadow-[var(--shadow-card)]">
      <div className="rounded-[10px] bg-surface-2 px-4 py-3 ring-1 ring-white/[0.04] ring-inset">
        <p className="eyebrow">{label}</p>
        {loading ? (
          <div className="mt-3 h-8 w-20 animate-pulse rounded bg-surface-3" />
        ) : (
          <p className={cx("metric mt-2 text-2xl font-semibold tracking-tight", toneClass)}>
            {value}
          </p>
        )}
        {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
      </div>
    </div>
  );
}
