"use client";

import { useAuth } from "@/components/auth/Auth";
import { CameraCheckIn } from "@/features/attendance/face/CameraCheckIn";

export default function CameraPage() {
  const { user } = useAuth();
  if (!user) return null;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-semibold text-text">Camera check-in</h1>
        <p className="mt-1 text-sm text-muted">
          Face verification with server-side matching and geofenced location checks. Detection runs
          in your browser; only one frame per submission is sent for verification.
        </p>
      </div>
      <CameraCheckIn />
    </div>
  );
}
