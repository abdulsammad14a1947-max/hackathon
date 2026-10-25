/** Response types for the M10 camera attendance endpoints (M10 contract). */

export interface FaceOfficeInfo {
  lat: number;
  lng: number;
  radius_m: number;
}

export interface FaceStatus {
  enrolled: boolean;
  template_version: number | null;
  model: string | null;
  enrolled_at: string | null;
  updated_at: string | null;
  match_threshold: number;
  engine_available: boolean;
  office: FaceOfficeInfo | null;
}

export interface FaceChallenge {
  nonce: string;
  token: string;
  expires_in: number;
}

export interface FaceLocationInfo {
  distance_m: number | null;
  accuracy_m: number;
  within_geofence: boolean | null;
}

export interface AttendanceRecord {
  id: number;
  date: string;
  check_in: string | null;
  check_out: string | null;
  status: string;
  display_status: string;
  missing_checkout: boolean;
  worked_hours: number;
  source: string;
}

export interface FaceResult {
  verified: boolean;
  purpose: string;
  similarity: number;
  match_threshold: number;
  detector_score: number;
  template_version: number;
  location?: FaceLocationInfo | null;
  attendance?: AttendanceRecord | null;
}

export interface FaceEnrollResult {
  enrolled: boolean;
  re_enrolled: boolean;
  template_version: number;
  model: string;
  enrolled_at: string | null;
  match_threshold: number;
}

/** Live state of the camera viewfinder (detection — NOT verification). */
export type FaceUiState =
  | "loading" // model / camera still starting
  | "unsupported" // no getUserMedia in this browser
  | "denied" // permission refused
  | "not_found" // no camera device
  | "failed" // camera could not start
  | "model_error" // MediaPipe model failed to load
  | "too_dark" // scene too dark for reliable detection
  | "no_face" // zero faces in frame
  | "multi_face" // more than one face
  | "too_small" // one face, but too far away
  | "ready" // exactly one usable face
  | "offline"; // camera live but detector not ready yet
