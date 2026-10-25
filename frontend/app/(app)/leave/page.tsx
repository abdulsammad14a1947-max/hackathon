"use client";

import { useAuth } from "@/components/auth/Auth";
import { EmployeeLeave, HrLeave } from "@/features/leave/LeaveFeature";

export default function LeavePage() {
  const { user } = useAuth();
  if (!user) return null;

  if (user.role === "employee") return <EmployeeLeave />;
  return <HrLeave />;
}
