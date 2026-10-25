"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth, RequireRole } from "@/components/auth/Auth";
import { PayrollIndex } from "@/features/payroll/PayrollFeature";
import { PageSkeleton } from "@/components/ui/Skeleton";

export default function PayrollPage() {
  const { user } = useAuth();
  const router = useRouter();

  // Employees never see payroll — their entry point is /payslips.
  useEffect(() => {
    if (user && user.role === "employee") router.replace("/payslips");
  }, [user, router]);

  if (!user) return null;
  if (user.role === "employee") return <PageSkeleton />;

  return (
    <RequireRole roles={["admin", "hr"]}>
      <PayrollIndex />
    </RequireRole>
  );
}
