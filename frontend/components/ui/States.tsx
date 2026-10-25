import { cx } from "@/lib/utils";

export function EmptyState({
  title,
  description,
  action,
  icon,
  compact,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
  icon?: React.ReactNode;
  compact?: boolean;
}) {
  return (
    <div
      className={cx(
        "flex flex-col items-center justify-center rounded-lg border border-dashed border-border text-center",
        compact ? "px-4 py-6" : "px-6 py-12",
      )}
    >
      <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-surface-3 text-muted">
        {icon ?? <span aria-hidden>∅</span>}
      </div>
      <p className="text-sm font-medium text-text">{title}</p>
      {description && <p className="mt-1 max-w-md text-xs leading-relaxed text-muted">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({
  title = "Something went wrong",
  message,
  onRetry,
}: {
  title?: string;
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center justify-center rounded-lg border border-danger/30 bg-danger/5 px-6 py-10 text-center"
    >
      <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-danger/15 text-danger">
        <span aria-hidden>!</span>
      </div>
      <p className="text-sm font-medium text-text">{title}</p>
      <p className="mt-1 max-w-md text-xs leading-relaxed text-muted">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-4 rounded-lg border border-danger/40 bg-danger/15 px-4 py-2 text-sm font-medium text-danger transition-[background-color,transform] duration-200 ease-snappy hover:bg-danger/25 active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-bg"
        >
          Retry
        </button>
      )}
    </div>
  );
}
