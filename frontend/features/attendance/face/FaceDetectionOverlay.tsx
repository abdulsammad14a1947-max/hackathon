"use client";

import { cx } from "@/lib/utils";
import type { FaceBox } from "@/lib/faceVision";

/**
 * Camera viewfinder: video preview + brass corner brackets around the face.
 *
 * The preview is mirrored with CSS for a natural selfie feel; the frame that
 * gets uploaded is captured un-mirrored (see `captureFrame`).
 *
 * Coordinate mapping: the wrapper adopts the stream's aspect ratio, so the
 * detector's normalised bounding box maps 1:1 to CSS percentages — no crop
 * math needed.
 */
export function FaceDetectionOverlay({
  videoRef,
  box,
  frame,
  live,
  ready,
  onLoadedMetadata,
  children,
}: {
  videoRef: React.RefObject<HTMLVideoElement | null>;
  /** normalised face box (0..1) from the browser detector, null when absent */
  box: FaceBox | null;
  /** intrinsic video frame size once known */
  frame: { w: number; h: number } | null;
  /** camera stream is playing */
  live: boolean;
  /** exactly one usable face in frame */
  ready: boolean;
  /** reports the stream's intrinsic size so the wrapper can adopt its ratio */
  onLoadedMetadata?: (size: { w: number; h: number }) => void;
  children?: React.ReactNode;
}) {
  // Guide frame shown while searching for a face (portrait-ish face oval box).
  const guide = { x: 0.27, y: 0.14, w: 0.46, h: 0.62 };
  const target = box ?? guide;

  // Expand the brackets slightly beyond the face so they never clip features.
  const padX = box ? Math.max(target.w * 0.12, 0.015) : 0;
  const padY = box ? Math.max(target.h * 0.08, 0.015) : 0;
  const left = Math.max(0, target.x - padX);
  const top = Math.max(0, target.y - padY);
  const right = Math.min(1, target.x + target.w + padX);
  const bottom = Math.min(1, target.y + target.h + padY);

  return (
    <div
      className="relative w-full overflow-hidden rounded-2xl border border-border bg-black shadow-[var(--shadow-card)]"
      style={frame && frame.w > 0 ? { aspectRatio: `${frame.w} / ${frame.h}` } : { aspectRatio: "4 / 3" }}
      data-testid="camera-viewfinder"
    >
      <video
        ref={videoRef}
        playsInline
        muted
        autoPlay
        onLoadedMetadata={(e) => {
          const v = e.currentTarget;
          if (v.videoWidth && v.videoHeight) {
            onLoadedMetadata?.({ w: v.videoWidth, h: v.videoHeight });
          }
        }}
        className={cx(
          "h-full w-full object-cover transition-opacity duration-500 ease-snappy",
          "scale-x-[-1]", // mirrored preview (capture stays un-mirrored)
          live ? "opacity-100" : "opacity-0",
        )}
      />

      {/* Face brackets — always rendered so the layout never jumps */}
      <div
        aria-hidden
        className={cx(
          "pointer-events-none absolute transition-all duration-150 ease-snappy",
          box ? "opacity-100" : "opacity-40",
        )}
        style={{
          left: `${left * 100}%`,
          top: `${top * 100}%`,
          width: `${(right - left) * 100}%`,
          height: `${(bottom - top) * 100}%`,
        }}
      >
        {(
          [
            ["top-0 left-0 border-l-2 border-t-2 rounded-tl-md", "left-0 top-0"],
            ["top-0 right-0 border-r-2 border-t-2 rounded-tr-md", "right-0 top-0"],
            ["bottom-0 left-0 border-l-2 border-b-2 rounded-bl-md", "left-0 bottom-0"],
            ["bottom-0 right-0 border-r-2 border-b-2 rounded-br-md", "right-0 bottom-0"],
          ] as const
        ).map(([cls, pos]) => (
          <span
            key={pos}
            className={cx(
              "absolute h-7 w-7 transition-colors duration-200 ease-snappy",
              pos,
              cls,
              ready ? "border-success" : box ? "border-accent" : "border-white/50",
            )}
          />
        ))}
      </div>

      {/* Status pill — children own the text (detection vs verification copy) */}
      {children}
    </div>
  );
}
