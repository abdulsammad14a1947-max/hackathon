"use client";

import { useAuth } from "@/components/auth/Auth";
import { EmployeeAttendance } from "@/features/attendance/EmployeeAttendance";
import { HrAttendance } from "@/features/attendance/HrAttendance";

export default function AttendancePage() {
  const { user } = useAuth();
  if (!user) return null;

  if (user.role === "employee") return <EmployeeAttendance />;
  return <HrAttendance />;
}
