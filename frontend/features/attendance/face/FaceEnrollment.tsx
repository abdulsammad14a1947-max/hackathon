"use client";

import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/layout/Icon";
import type { FaceEnrollResult, FaceStatus, FaceUiState } from "./types";

/**
 * Enrolment panel (enroll tab content). Enrollment is authenticated and
 * self-only: the backend binds the template to the session's employee, allows
 * re-enrollment (version bump), and stores no photographs — only the protected
 * 128-d template.
 */
export function FaceEnrollment({
  status,
  statusLoading,
  faceState,
  busy,
  result,
  onEnroll,
}: {
  status: FaceStatus | undefined;
  statusLoading: boolean;
  faceState: FaceUiState;
  busy: boolean;
  result: FaceEnrollResult | null;
  onEnroll: () => void;
}) {
  const faceReady = faceState === "ready";
  const engineDown = status !== undefined && !status.engine_available;

  return (
    <div className="space-y-4">
      <div className="flex items-start gap-3 rounded-lg border border-border bg-surface-2/60 px-4 py-3">
        <Icon
          name={status?.enrolled ? "check" : "key"}
          className={`mt-0.5 h-4 w-4 shrink-0 ${status?.enrolled ? "text-success" : "text-accent"}`}
        />
        <div className="min-w-0">
          {statusLoading ? (
            <p className="text-xs text-muted">Checking enrolment status…</p>
          ) : status?.enrolled ? (
            <>
              <p className="text-xs font-medium text-text">
                Face enrolled — template v{status.template_version}
                {status.updated_at && (
                  <span className="ml-2 font-normal text-muted">
                    updated {status.updated_at.slice(0, 10)}
                  </span>
                )}
              </p>
              <p className="mt-1 text-xs leading-relaxed text-muted">
                Only your protected face template is stored — no photographs. Capture again any
                time to re-enrol (this replaces the template and bumps the version).
              </p>
            </>
          ) : (
            <>
              <p className="text-xs font-medium text-text">Not enrolled yet</p>
              <p className="mt-1 text-xs leading-relaxed text-muted">
                Look straight at the camera in good light and capture one frame. The server will
                detect, align and embed your face — nothing is saved until it passes the quality
                gate.
              </p>
            </>
          )}
        </div>
      </div>

      {engineDown && (
        <div className="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-xs leading-relaxed text-danger">
          The server face engine is unavailable (model files missing). Run{" "}
          <code className="rounded bg-danger/15 px-1 py-0.5">python -m app.face.models</code> in
          the backend, then reload.
        </div>
      )}

      {result && (
        <div
          role="status"
          className="flex items-center gap-3 rounded-lg border border-success/40 bg-success/10 px-4 py-3 text-xs"
        >
          <Icon name="check" className="h-4 w-4 shrink-0 text-success" />
          <span className="text-text">
            {result.re_enrolled ? "Re-enrolled" : "Enrolled"} — template v
            {result.template_version} ({result.model}). Match threshold{" "}
            {result.match_threshold.toFixed(2)}.
          </span>
        </div>
      )}

      <Button
        className="w-full"
        size="lg"
        onClick={onEnroll}
        loading={busy}
        disabled={busy || !faceReady || engineDown}
      >
        {status?.enrolled ? "Re-capture face template" : "Capture face template"}
      </Button>
      {!faceReady && !engineDown && (
        <p className="text-center text-xs text-muted">
          The capture button activates when exactly one face is detected in the viewfinder.
        </p>
      )}
    </div>
  );
}
