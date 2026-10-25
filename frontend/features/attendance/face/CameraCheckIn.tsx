"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { FaceDetector } from "@mediapipe/tasks-vision";

import { api, ApiError, errorMessage } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { useToast } from "@/components/ui/Toast";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Icon } from "@/components/layout/Icon";
import { cx } from "@/lib/utils";
import {
  CameraError,
  captureFrame,
  detectFaces,
  loadFaceDetector,
  measureBrightness,
  requestLocation,
  startCamera,
  stopCamera,
  type FaceBox,
} from "@/lib/faceVision";

import { FaceDetectionOverlay } from "./FaceDetectionOverlay";
import { FaceVerificationStatus } from "./FaceVerificationStatus";
import { LocationVerificationStatus, type LocationState } from "./LocationVerificationStatus";
import { AttendanceResult } from "./AttendanceResult";
import { FaceEnrollment } from "./FaceEnrollment";
import type {
  FaceEnrollResult,
  FaceResult,
  FaceStatus,
  FaceUiState,
} from "./types";

type Mode = "check-in" | "check-out" | "enroll";

const TABS: { id: Mode; label: string }[] = [
  { id: "check-in", label: "Check in" },
  { id: "check-out", label: "Check out" },
  { id: "enroll", label: "Enrol face" },
];

const ROUTE: Record<Mode, string> = {
  "check-in": "/api/attendance/face/check-in",
  "check-out": "/api/attendance/face/check-out",
  enroll: "/api/attendance/face/enroll",
};

/**
 * Camera attendance viewfinder (M10).
 *
 * Browser side: live face DETECTION (MediaPipe, model bundled in /public) for
 * instant guidance only. Verification always happens on the server, which
 * receives exactly one JPEG frame + GPS per submission together with a
 * single-use challenge token — no video ever leaves the device.
 */
export function CameraCheckIn() {
  const toast = useToast();
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const detectorRef = useRef<FaceDetector | null>(null);

  const statusApi = useApi<FaceStatus>("/api/attendance/face/status");
  const status = statusApi.data;

  const [mode, setMode] = useState<Mode>("check-in");
  const [faceState, setFaceState] = useState<FaceUiState>("loading");
  const [detectorReady, setDetectorReady] = useState(false);
  const [cameraLive, setCameraLive] = useState(false);
  const [box, setBox] = useState<FaceBox | null>(null);
  const [frame, setFrame] = useState<{ w: number; h: number } | null>(null);
  const [loc, setLoc] = useState<LocationState>({ status: "idle" });
  const [busy, setBusy] = useState<Mode | null>(null);
  const [result, setResult] = useState<FaceResult | null>(null);
  const [enrollResult, setEnrollResult] = useState<FaceEnrollResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const faceReady = faceState === "ready";
  const isCheckMode = mode !== "enroll";
  const enrolled = status?.enrolled ?? false;
  const engineDown = status !== undefined && !status.engine_available;

  // ---- camera + detector lifecycle --------------------------------------- //
  const boot = useCallback(async () => {
    setError(null);
    setFaceState("loading");
    setDetectorReady(false);

    if (streamRef.current) return; // already live (e.g. tab switch back)

    try {
      const stream = await startCamera();
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        void videoRef.current.play().catch(() => undefined);
      }
      setCameraLive(true);
    } catch (err) {
      setCameraLive(false);
      setFaceState(
        err instanceof CameraError
          ? err.code === "unsupported"
            ? "unsupported"
            : err.code === "denied"
              ? "denied"
              : err.code === "not_found"
                ? "not_found"
                : "failed"
          : "failed",
      );
      setError(err instanceof Error ? err.message : "Could not start the camera.");
      return;
    }

    try {
      detectorRef.current = await loadFaceDetector();
      setDetectorReady(true);
      setFaceState("no_face"); // live frames, waiting for the first face
    } catch {
      setFaceState("model_error");
      setError(
        "The face detection model could not be loaded. Check your connection and reload the page.",
      );
    }
  }, []);

  const shutdown = useCallback(() => {
    stopCamera(streamRef.current);
    streamRef.current = null;
    setCameraLive(false);
    setDetectorReady(false);
    setBox(null);
  }, []);

  // Start once on mount; release the camera on unmount (route change).
  useEffect(() => {
    void boot();
    return () => {
      stopCamera(streamRef.current);
      streamRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- boot once per mount
  }, []);

  // Auto-acquire location once (the server requires GPS for check-in/out).
  const locate = useCallback(async () => {
    setLoc({ status: "locating" });
    try {
      const coords = await requestLocation();
      setLoc({ status: "ok", coords });
    } catch (err) {
      setLoc({ status: "error", message: (err as Error).message });
    }
  }, []);

  useEffect(() => {
    void locate();
  }, [locate]);

  // ---- detection loop (browser-side guidance only) ----------------------- //
  useEffect(() => {
    if (!cameraLive || !detectorReady) return;
    let cancelled = false;

    const tick = () => {
      const video = videoRef.current;
      const detector = detectorRef.current;
      if (cancelled || !video || !detector || video.readyState < 2) return;
      try {
        const found = detectFaces(detector, video);
        setBox(found.box);
        const brightness = measureBrightness(video);
        if (brightness > 0 && brightness < 45) setFaceState("too_dark");
        else if (found.count === 0) setFaceState("no_face");
        else if (found.count > 1) setFaceState("multi_face");
        else if (found.box && (found.box.w < 0.14 || found.box.h < 0.18))
          setFaceState("too_small");
        else setFaceState("ready");
      } catch {
        // transient per-frame decode errors: keep the previous state
      }
    };

    tick();
    const id = window.setInterval(tick, 250);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [cameraLive, detectorReady]);

  // ---- submission -------------------------------------------------------- //
  const submit = useCallback(
    async (target: Mode) => {
      if (busy) return;
      setBusy(target);
      setError(null);
      if (target !== "enroll") setResult(null);
      try {
        const video = videoRef.current;
        if (!video) throw new Error("The camera is not ready yet.");
        const blob = await captureFrame(video);

        // fresh single-use challenge per submission (anti-replay)
        const challenge = await api<{ nonce: string; token: string }>("/api/attendance/face/challenge", {
          method: "POST",
        });

        const fd = new FormData();
        fd.append("file", blob, "frame.jpg");
        fd.append("nonce", challenge.nonce);
        fd.append("token", challenge.token);
        if (loc.status === "ok") {
          fd.append("lat", String(loc.coords.lat));
          fd.append("lng", String(loc.coords.lng));
          fd.append("accuracy_m", String(loc.coords.accuracy_m));
        }

        if (target === "enroll") {
          const res = await api<FaceEnrollResult>(ROUTE.enroll, { method: "POST", formData: fd });
          setEnrollResult(res);
          statusApi.reload();
          toast({
            type: "success",
            message: `Face ${res.re_enrolled ? "re-enrolled" : "enrolled"} — template v${res.template_version}.`,
          });
        } else {
          const res = await api<FaceResult>(ROUTE[target], { method: "POST", formData: fd });
          setResult(res);
          shutdown(); // release the camera after a successful punch
          toast({
            type: "success",
            message:
              target === "check-in"
                ? "Checked in with server-side face verification."
                : "Checked out with server-side face verification.",
          });
        }
      } catch (err) {
        // Prefer the backend's precise detail (403 responses get a generic
        // message from the shared client, so read `detail` when present).
        const msg =
          err instanceof ApiError && typeof err.detail === "string" && err.detail
            ? err.detail
            : errorMessage(err);
        setError(msg);
      } finally {
        setBusy(null);
      }
    },
    [busy, loc, shutdown, statusApi, toast],
  );

  const switchMode = (next: Mode) => {
    setMode(next);
    setError(null);
    setResult(null);
    setEnrollResult(null);
  };

  const reset = () => {
    setResult(null);
    setError(null);
    void boot();
  };

  // ---- guards ------------------------------------------------------------- //
  const checkBlockedReason = !faceReady
    ? "Waiting for exactly one face in the viewfinder."
    : loc.status !== "ok"
      ? "Location is required — allow GPS access, then refresh."
      : status === undefined
        ? "Checking enrolment status…"
        : !enrolled
          ? "Enrol your face first (Enrol face tab)."
          : engineDown
            ? "The server face engine is offline — see the enrolment tab."
            : null;

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_380px]">
      {/* ---------------- viewfinder column ---------------- */}
      <div className="space-y-4">
        <FaceDetectionOverlay
          videoRef={videoRef}
          box={box}
          frame={frame}
          live={cameraLive}
          ready={faceReady && !busy}
          onLoadedMetadata={setFrame}
        >
          <FaceVerificationStatus
            state={faceState}
            submitting={busy !== null}
            verified={result !== null && result.purpose !== "enroll"}
          />
        </FaceDetectionOverlay>

        {error && (faceState === "denied" || faceState === "unsupported" || faceState === "not_found" || faceState === "failed" || faceState === "model_error") && (
          <div
            role="alert"
            className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-danger/40 bg-danger/10 px-5 py-4"
          >
            <div className="flex items-start gap-3">
              <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-danger/20 text-danger">
                <Icon name="info" className="h-4 w-4" />
              </span>
              <div>
                <p className="text-sm font-semibold text-text">Camera unavailable</p>
                <p className="mt-1 text-sm leading-relaxed text-muted">{error}</p>
              </div>
            </div>
            <Button size="sm" onClick={() => void boot()}>
              Try again
            </Button>
          </div>
        )}

        {isCheckMode && loc.status !== "idle" && (
          <LocationVerificationStatus
            state={loc}
            office={status?.office ?? null}
            onLocate={() => void locate()}
            disabled={busy !== null}
          />
        )}

        {isCheckMode && (
          <AttendanceResult
            result={result}
            error={error && !cameraUnavailable(faceState) ? error : null}
            onRetry={() => (result ? reset() : void submit(mode))}
            onReset={reset}
            busy={busy !== null}
          />
        )}

        {!isCheckMode && error && cameraUnavailable(faceState) === false && (
          <div
            role="alert"
            className="rounded-xl border border-danger/40 bg-danger/10 px-5 py-4 text-sm leading-relaxed text-muted"
          >
            <span className="font-semibold text-text">Enrolment failed: </span>
            {error}
          </div>
        )}
      </div>

      {/* ---------------- controls column ---------------- */}
      <div className="space-y-4">
        <Card
          title="Camera attendance"
          description="One frame per request — verified on the server against your enrolled template."
        >
          <div
            role="tablist"
            aria-label="Camera attendance mode"
            className="mb-4 flex rounded-lg border border-border bg-surface-2 p-1"
          >
            {TABS.map((tab) => (
              <button
                key={tab.id}
                role="tab"
                type="button"
                aria-selected={mode === tab.id}
                onClick={() => switchMode(tab.id)}
                className={cx(
                  "flex-1 rounded-md px-3 py-2 text-xs font-medium transition-colors duration-200 ease-snappy",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-1 focus-visible:ring-offset-bg",
                  mode === tab.id
                    ? "bg-surface text-text shadow-[var(--shadow-card)]"
                    : "text-muted hover:text-text",
                )}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {mode === "enroll" ? (
            <FaceEnrollment
              status={status}
              statusLoading={statusApi.loading}
              faceState={faceState}
              busy={busy === "enroll"}
              result={enrollResult}
              onEnroll={() => void submit("enroll")}
            />
          ) : (
            <div className="space-y-4">
              <div className="flex items-center justify-between rounded-lg border border-border bg-surface-2/60 px-4 py-3">
                <div>
                  <p className="text-xs font-medium text-text">Enrolment</p>
                  <p className="mt-0.5 text-xs text-muted">
                    {enrolled
                      ? `Template v${status?.template_version} on file`
                      : "No face template yet"}
                  </p>
                </div>
                <Badge tone={enrolled ? "ok" : "warn"}>
                  {enrolled ? "ready" : "not enrolled"}
                </Badge>
              </div>

              <Button
                className="w-full"
                size="lg"
                onClick={() => void submit(mode)}
                loading={busy === mode}
                disabled={busy !== null || checkBlockedReason !== null}
              >
                <span className="inline-flex items-center gap-2">
                  <Icon name={mode === "check-in" ? "attendance" : "check"} className="h-4 w-4" />
                  {mode === "check-in" ? "Check in with face" : "Check out with face"}
                </span>
              </Button>

              {checkBlockedReason && (
                <p className="text-center text-xs leading-relaxed text-muted" aria-live="polite">
                  {checkBlockedReason}
                </p>
              )}
            </div>
          )}
        </Card>

        <Card title="How it works" bodyClassName="pt-5">
          <ol className="space-y-2.5 text-xs leading-relaxed text-muted">
            {[
              "Your browser detects a face locally (green brackets) — video never leaves the device.",
              "You grant location once; the server re-checks GPS accuracy (≤100 m) and the office geofence.",
              "On submit, one JPEG frame + a single-use challenge token go to the server.",
              "The server detects, aligns and matches your face against your enrolled template (cosine ≥ threshold) and applies the normal attendance rules.",
            ].map((text, i) => (
              <li key={i} className="flex gap-2.5">
                <span className="mt-px flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-accent/15 text-[10px] font-semibold text-accent">
                  {i + 1}
                </span>
                <span>{text}</span>
              </li>
            ))}
          </ol>
          <p className="mt-3 border-t border-border pt-3 text-[11px] leading-relaxed text-muted/80">
            Privacy: enrolment stores a protected 128-dimension template — never photographs — and
            only you (via your own login) can enrol or use it. Face matching is verification-only
            (1:1), not identification; it is not foolproof against spoofing with a printed photo or
            another screen (see docs/face-attendance.md).
          </p>
        </Card>
      </div>
    </div>
  );
}

function cameraUnavailable(state: FaceUiState): boolean {
  return (
    state === "denied" ||
    state === "unsupported" ||
    state === "not_found" ||
    state === "failed" ||
    state === "model_error"
  );
}
