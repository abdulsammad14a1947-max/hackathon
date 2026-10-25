"use client";

import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/layout/Icon";
import { Badge } from "@/components/ui/Badge";
import type { FaceResult } from "./types";

const STATUS_TONE: Record<string, "ok" | "warn" | "danger" | "info" | "neutral"> = {
  present: "ok",
  late: "warn",
  half_day: "warn",
  absent: "danger",
  leave: "info",
  weekend: "neutral",
  holiday: "neutral",
};

/**
 * Outcome panel after a submission: success shows the SERVER-computed record
 * and match score; failure shows the backend's reason with a retry action.
 * Nothing here is computed on the client.
 */
export function AttendanceResult({
  result,
  error,
  onRetry,
  onReset,
  busy,
}: {
  result: FaceResult | null;
  error: string | null;
  onRetry: () => void;
  onReset: () => void;
  busy: boolean;
}) {
  if (error) {
    return (
      <div
        role="alert"
        className="flex flex-col gap-3 rounded-xl border border-danger/40 bg-danger/10 px-5 py-4"
      >
        <div className="flex items-start gap-3">
          <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-danger/20 text-danger">
            <Icon name="info" className="h-4 w-4" />
          </span>
          <div>
            <p className="text-sm font-semibold text-text">Verification did not pass</p>
            <p className="mt-1 text-sm leading-relaxed text-muted">{error}</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2 pl-11">
          <Button size="sm" onClick={onRetry} loading={busy}>
            Try again
          </Button>
          <Button size="sm" variant="secondary" onClick={onReset}>
            Back to camera
          </Button>
        </div>
      </div>
    );
  }

  if (!result) return null;

  const att = result.attendance;
  const label =
    result.purpose === "check_in"
      ? "Checked in"
      : result.purpose === "check_out"
        ? "Checked out"
        : "Verification passed";

  return (
    <div
      role="status"
      className="flex flex-col gap-3 rounded-xl border border-success/40 bg-success/10 px-5 py-4"
    >
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-success/20 text-success">
          <Icon name="check" className="h-4 w-4" />
        </span>
        <div className="min-w-0">
          <p className="text-sm font-semibold text-text">{label}</p>
          <p className="mt-1 text-sm leading-relaxed text-muted">
            {att ? (
              <>
                {att.check_in && <>In {att.check_in.replace("T", " ").slice(0, 16)} · </>}
                {att.check_out && <>Out {att.check_out.replace("T", " ").slice(0, 16)} · </>}
                <Badge tone={STATUS_TONE[att.display_status] ?? "neutral"}>
                  {att.display_status.replace(/_/g, " ")}
                </Badge>
                {att.source === "face_camera" && (
                  <span className="ml-2 text-xs text-muted">via camera</span>
                )}
              </>
            ) : (
              "Face matched your enrolled template on the server."
            )}
          </p>
        </div>
      </div>

      <dl className="flex flex-wrap gap-x-6 gap-y-1.5 pl-11 text-xs text-muted">
        <div className="flex gap-1.5">
          <dt className="text-muted/80">Match</dt>
          <dd className="font-medium text-text">
            {result.similarity.toFixed(3)} ≥ {result.match_threshold.toFixed(2)}
          </dd>
        </div>
        <div className="flex gap-1.5">
          <dt className="text-muted/80">Detector</dt>
          <dd className="font-medium text-text">{result.detector_score.toFixed(2)}</dd>
        </div>
        {result.location && (
          <div className="flex gap-1.5">
            <dt className="text-muted/80">Position</dt>
            <dd className="font-medium text-text">
              ±{result.location.accuracy_m} m
              {result.location.distance_m !== null &&
                ` · ${Math.round(result.location.distance_m)} m from office`}
            </dd>
          </div>
        )}
        <div className="flex gap-1.5">
          <dt className="text-muted/80">Template</dt>
          <dd className="font-medium text-text">v{result.template_version}</dd>
        </div>
      </dl>

      <div className="pl-11">
        <Button size="sm" variant="secondary" onClick={onReset}>
          {result.purpose === "verify" ? "Back to camera" : "Done"}
        </Button>
      </div>
    </div>
  );
}
