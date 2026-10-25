import { cx, statusTone, titleCase } from "@/lib/utils";

type Tone = "ok" | "warn" | "danger" | "info" | "neutral" | "accent";

const TONES: Record<Tone, string> = {
  ok: "bg-success/12 text-success border-success/30",
  warn: "bg-warning/12 text-warning border-warning/30",
  danger: "bg-danger/12 text-danger border-danger/30",
  info: "bg-info/12 text-info border-info/30",
  neutral: "bg-surface-3 text-muted border-border-strong",
  accent: "bg-accent/15 text-accent border-accent/40",
};

export function Badge({
  children,
  tone = "neutral",
  className,
  title,
}: {
  children: React.ReactNode;
  tone?: Tone;
  className?: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={cx(
        "inline-flex items-center whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize",
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

/** Badge that derives its tone from a status string (present, pending, ...). */
export function StatusBadge({ status, label }: { status: string; label?: string }) {
  return <Badge tone={statusTone(status)}>{label ?? titleCase(status)}</Badge>;
}
