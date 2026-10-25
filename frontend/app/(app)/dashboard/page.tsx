"use client";

import { useAuth } from "@/components/auth/Auth";
import { AdminDashboard } from "@/features/dashboard/AdminDashboard";
import { HrDashboard } from "@/features/dashboard/HrDashboard";
import { EmployeeDashboard } from "@/features/dashboard/EmployeeDashboard";

export default function DashboardPage() {
  const { user } = useAuth();

  if (!user) return null;

  if (user.role === "admin") return <AdminDashboard />;
  if (user.role === "hr") return <HrDashboard />;
  return <EmployeeDashboard />;
}
