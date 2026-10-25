"use client";

/**
 * Camera + face-detection helpers for the M10 camera check-in page.
 *
 * - Detection runs **in the browser** (MediaPipe Tasks Vision, model served
 *   from /public/models) so live feedback is instant and no video ever leaves
 *   the device — only a single captured JPEG frame is uploaded for
 *   server-side verification.
 * - Detection (a face is present) is NOT verification (it matches the
 *   enrolled employee): that decision is made by the backend.
 */
import { FaceDetector, FilesetResolver } from "@mediapipe/tasks-vision";

// --------------------------------------------------------------------------- //
// Face detection (MediaPipe)
// --------------------------------------------------------------------------- //
let detectorPromise: Promise<FaceDetector> | null = null;

export async function loadFaceDetector(): Promise<FaceDetector> {
  if (!detectorPromise) {
    detectorPromise = (async () => {
      const fileset = await FilesetResolver.forVisionTasks("/vision/wasm");
      const make = (delegate: "GPU" | "CPU") =>
        FaceDetector.createFromOptions(fileset, {
          baseOptions: {
            modelAssetPath: "/models/face_detection_short_range.tflite",
            delegate,
          },
          runningMode: "VIDEO",
          minDetectionConfidence: 0.5,
        });
      // GPU delegate is faster but unavailable in some browsers — fall back.
      try {
        return await make("GPU");
      } catch {
        return await make("CPU");
      }
    })();
    // clear so a failed load (offline, blocked wasm) can be retried
    detectorPromise.catch(() => {
      detectorPromise = null;
    });
  }
  return detectorPromise;
}

export interface FaceBox {
  x: number;
  y: number;
  w: number;
  h: number;
  score: number;
}

export interface DetectionResult {
  /** number of faces above the detector confidence */
  count: number;
  /** largest face, normalised to the video frame (null when count === 0) */
  box: FaceBox | null;
}

let lastVideoTs = 0;

export function detectFaces(detector: FaceDetector, video: HTMLVideoElement): DetectionResult {
  if (video.readyState < 2) return { count: 0, box: null };
  // detectForVideo requires strictly increasing timestamps
  const ts = Math.max(performance.now(), lastVideoTs + 1);
  lastVideoTs = ts;
  const res = detector.detectForVideo(video, ts);
  const detections = res.detections ?? [];
  if (detections.length === 0) return { count: 0, box: null };

  const boxes: FaceBox[] = detections.map((d) => {
    const b = d.boundingBox;
    const score = d.categories?.[0]?.score ?? 0;
    return {
      x: b?.originX ?? 0,
      y: b?.originY ?? 0,
      w: b?.width ?? 0,
      h: b?.height ?? 0,
      score,
    };
  });
  const best = boxes.reduce((a, b) => (b.w * b.h > a.w * a.h ? b : a));
  return { count: boxes.length, box: best };
}

/** Average luminance (0–255) of the current frame — used for the poor-light hint. */
export function measureBrightness(video: HTMLVideoElement): number {
  if (video.readyState < 2) return 0;
  const canvas = document.createElement("canvas");
  canvas.width = 32;
  canvas.height = 18;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return 0;
  ctx.drawImage(video, 0, 0, 32, 18);
  const { data } = ctx.getImageData(0, 0, 32, 18);
  let sum = 0;
  for (let i = 0; i < data.length; i += 4) {
    sum += 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
  }
  return Math.round(sum / (data.length / 4));
}

// --------------------------------------------------------------------------- //
// Camera lifecycle
// --------------------------------------------------------------------------- //
export type CameraErrorCode = "unsupported" | "insecure" | "denied" | "not_found" | "failed";

export class CameraError extends Error {
  code: CameraErrorCode;
  constructor(code: CameraErrorCode, message: string) {
    super(message);
    this.name = "CameraError";
    this.code = code;
  }
}

export function isCameraSupported(): boolean {
  return (
    typeof navigator !== "undefined" &&
    !!navigator.mediaDevices &&
    typeof navigator.mediaDevices.getUserMedia === "function"
  );
}

export async function startCamera(): Promise<MediaStream> {
  if (!isCameraSupported()) {
    throw new CameraError(
      "unsupported",
      "This browser does not support camera access. Try Chrome, Edge or Safari on HTTPS.",
    );
  }
  if (typeof window !== "undefined" && !window.isSecureContext) {
    throw new CameraError(
      "insecure",
      "Camera access requires a secure context (HTTPS or localhost).",
    );
  }
  try {
    return await navigator.mediaDevices.getUserMedia({
      video: {
        facingMode: { ideal: "user" }, // front camera where supported
        width: { ideal: 1280 },
        height: { ideal: 720 },
      },
      audio: false,
    });
  } catch (err) {
    const e = err as DOMException;
    if (e.name === "NotAllowedError" || e.name === "SecurityError") {
      throw new CameraError("denied", "Camera permission was denied. Allow camera access in your browser and try again.");
    }
    if (e.name === "NotFoundError" || e.name === "OverconstrainedError") {
      throw new CameraError("not_found", "No camera was found on this device.");
    }
    if (e.name === "NotReadableError" || e.name === "AbortError") {
      throw new CameraError("failed", "The camera is busy in another app or could not be started.");
    }
    throw new CameraError("failed", "Could not start the camera.");
  }
}

/** Stop every track — called on unmount, on success and before navigation. */
export function stopCamera(stream: MediaStream | null | undefined): void {
  stream?.getTracks().forEach((track) => track.stop());
}

/**
 * Grab ONE frame as JPEG. The preview is mirrored with CSS for a natural
 * selfie feel, but the captured bytes are NOT mirrored so the server matches
 * the same geometry it enrolled.
 */
export function captureFrame(video: HTMLVideoElement, quality = 0.92): Promise<Blob> {
  const width = video.videoWidth;
  const height = video.videoHeight;
  if (!width || !height) {
    return Promise.reject(new CameraError("failed", "Camera frame is not ready yet."));
  }
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return Promise.reject(new CameraError("failed", "Canvas is unavailable."));
  ctx.drawImage(video, 0, 0, width, height); // true-to-scene (no mirror flip)
  return new Promise((resolve, reject) =>
    canvas.toBlob(
      (blob) =>
        blob ? resolve(blob) : reject(new CameraError("failed", "Could not read the camera frame.")),
      "image/jpeg",
      quality,
    ),
  );
}

// --------------------------------------------------------------------------- //
// Location (display only — the server re-validates GPS)
// --------------------------------------------------------------------------- //
export interface Coords {
  lat: number;
  lng: number;
  accuracy_m: number;
}

export function requestLocation(): Promise<Coords> {
  return new Promise((resolve, reject) => {
    if (typeof navigator === "undefined" || !("geolocation" in navigator)) {
      reject(new Error("This browser does not support location access."));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) =>
        resolve({
          lat: pos.coords.latitude,
          lng: pos.coords.longitude,
          accuracy_m: Math.round(pos.coords.accuracy ?? 0),
        }),
      (err) => {
        if (err.code === 1) reject(new Error("Location permission was denied."));
        else if (err.code === 2) reject(new Error("Your location could not be determined."));
        else reject(new Error("Location request timed out."));
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 },
    );
  });
}

/** Great-circle metres — DISPLAY estimate only; the server computes its own. */
export function haversineMeters(a: { lat: number; lng: number }, b: { lat: number; lng: number }): number {
  const R = 6371000;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const s =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(s));
}
