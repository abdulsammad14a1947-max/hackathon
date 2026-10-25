"use client";

import { Icon } from "@/components/layout/Icon";
import { cx } from "@/lib/utils";
import type { FaceUiState } from "./types";

const COPY: Record<FaceUiState, { text: string; tone: "ok" | "warn" | "bad" | "neutral" }> = {
  loading: { text: "Starting camera…", tone: "neutral" },
  offline: { text: "Face detector warming up…", tone: "neutral" },
  unsupported: { text: "Camera not supported in this browser", tone: "bad" },
  denied: { text: "Camera permission denied", tone: "bad" },
  not_found: { text: "No camera found on this device", tone: "bad" },
  failed: { text: "Camera could not start", tone: "bad" },
  model_error: { text: "Face detection model failed to load", tone: "bad" },
  too_dark: { text: "Too dark — improve the lighting", tone: "warn" },
  no_face: { text: "No face detected", tone: "warn" },
  multi_face: { text: "More than one face — only one person allowed", tone: "warn" },
  too_small: { text: "Move closer to the camera", tone: "warn" },
  ready: { text: "Face detected", tone: "ok" },
};

const TONE_CLASS: Record<string, string> = {
  ok: "border-success/50 bg-success/15 text-success",
  warn: "border-warning/50 bg-warning/15 text-warning",
  bad: "border-danger/50 bg-danger/15 text-danger",
  neutral: "border-border-strong bg-surface-2/90 text-muted backdrop-blur",
};

/**
 * Viewfinder status pill — shows *detection* state only. Verification is a
 * server decision and is reported separately (`verified`), so the UI never
 * claims "verified" before the backend says so.
 */
export function FaceVerificationStatus({
  state,
  submitting,
  verified,
  className,
}: {
  state: FaceUiState;
  submitting: boolean;
  verified: boolean;
  className?: string;
}) {
  const tone = verified
    ? "ok"
    : submitting
      ? "neutral"
      : COPY[state].tone;
  const text = verified
    ? "Identity verified by the server"
    : submitting
      ? "Verifying on the server…"
      : COPY[state].text;

  return (
    <div
      role="status"
      aria-live="polite"
      className={cx(
        "pointer-events-none absolute bottom-3 left-1/2 z-10 flex -translate-x-1/2 items-center gap-2",
        "rounded-full border px-3.5 py-1.5 text-xs font-medium shadow-lg backdrop-blur",
        TONE_CLASS[tone],
        className,
      )}
    >
      {verified ? (
        <Icon name="check" className="h-4 w-4" />
      ) : submitting ? (
        <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
      ) : state === "ready" ? (
        <Icon name="check" className="h-4 w-4" />
      ) : tone === "bad" ? (
        <Icon name="info" className="h-4 w-4" />
      ) : (
        <span className="h-1.5 w-1.5 rounded-full bg-current" />
      )}
      <span>{text}</span>
    </div>
  );
}
