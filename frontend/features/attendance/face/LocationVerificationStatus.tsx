"use client";

import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/layout/Icon";
import { cx } from "@/lib/utils";
import { haversineMeters, type Coords } from "@/lib/faceVision";
import type { FaceOfficeInfo } from "./types";

export type LocationState =
  | { status: "idle" }
  | { status: "locating" }
  | { status: "ok"; coords: Coords }
  | { status: "error"; message: string };

/**
 * Geofence status panel. Distances shown here are **display estimates** computed
 * in the browser — the server re-validates coordinates, accuracy (<=100 m) and
 * the Haversine distance against the office before recording attendance.
 */
export function LocationVerificationStatus({
  state,
  office,
  onLocate,
  disabled,
}: {
  state: LocationState;
  office: FaceOfficeInfo | null;
  onLocate: () => void;
  disabled?: boolean;
}) {
  const distance =
    state.status === "ok" && office
      ? haversineMeters(
          { lat: state.coords.lat, lng: state.coords.lng },
          { lat: office.lat, lng: office.lng },
        )
      : null;
  const outside = distance !== null && distance > office!.radius_m;

  if (state.status === "idle" || state.status === "error") {
    return (
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-surface-2/60 px-4 py-3">
        <div className="flex items-start gap-2.5">
          <Icon name="building" className="mt-0.5 h-4 w-4 shrink-0 text-muted" />
          <div className="min-w-0">
            <p className="text-xs font-medium text-text">
              {state.status === "error" ? "Location unavailable" : "Location required for check-in"}
            </p>
            <p className="mt-0.5 text-xs leading-relaxed text-muted">
              {state.status === "error"
                ? state.message
                : office
                  ? `The server checks your position against the office geofence (${office.radius_m} m radius).`
                  : "The server requires your GPS position (±100 m accuracy) to record attendance."}
            </p>
          </div>
        </div>
        <Button variant="secondary" size="sm" onClick={onLocate} disabled={disabled}>
          {state.status === "error" ? "Try again" : "Use my location"}
        </Button>
      </div>
    );
  }

  if (state.status === "locating") {
    return (
      <div className="flex items-center gap-2.5 rounded-lg border border-border bg-surface-2/60 px-4 py-3 text-xs text-muted">
        <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-accent border-t-transparent" />
        Getting your location…
      </div>
    );
  }

  const { coords } = state;
  return (
    <div
      className={cx(
        "flex flex-wrap items-center justify-between gap-3 rounded-lg border px-4 py-3",
        outside ? "border-warning/40 bg-warning/10" : "border-success/40 bg-success/10",
      )}
    >
      <div className="flex items-start gap-2.5">
        <Icon name="building" className={cx("mt-0.5 h-4 w-4 shrink-0", outside ? "text-warning" : "text-success")} />
        <div>
          <p className={cx("text-xs font-medium", outside ? "text-warning" : "text-success")}>
            GPS acquired ±{coords.accuracy_m} m
            {distance !== null && ` · ${Math.round(distance)} m from office`}
            {distance !== null && (outside ? " (outside geofence)" : " (within geofence)")}
          </p>
          <p className="mt-0.5 text-xs leading-relaxed text-muted">
            {coords.lat.toFixed(5)}, {coords.lng.toFixed(5)}
            {" — browser estimate; the server re-checks distance and accuracy."}
          </p>
        </div>
      </div>
      <Button variant="ghost" size="sm" onClick={onLocate} disabled={disabled}>
        Refresh
      </Button>
    </div>
  );
}
