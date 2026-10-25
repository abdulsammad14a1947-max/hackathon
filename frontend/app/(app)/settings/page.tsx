"use client";

import { useAuth, RequireRole } from "@/components/auth/Auth";
import { SettingsPage } from "@/features/settings/SettingsFeature";

export default function SettingsRoute() {
  const { user } = useAuth();

  // Employees never see settings.
  if (user && user.role === "employee") return null;

  return (
    <RequireRole roles={["admin", "hr"]}>
      <SettingsPage />
    </RequireRole>
  );
}
