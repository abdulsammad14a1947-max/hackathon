"use client";

import { RequireRole } from "@/components/auth/Auth";
import { AuditLogPage } from "@/features/audit/AuditLog";

export default function AuditRoute() {
  return (
    <RequireRole roles={["admin"]}>
      <AuditLogPage />
    </RequireRole>
  );
}
