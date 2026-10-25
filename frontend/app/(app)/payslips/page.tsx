"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth, RequireRole } from "@/components/auth/Auth";
import { PayslipList } from "@/features/payroll/Payslips";
import { PageSkeleton } from "@/components/ui/Skeleton";

export default function PayslipsPage() {
  const { user } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (user && user.role !== "employee") router.replace("/payroll");
  }, [user, router]);

  if (!user) return null;
  if (user.role !== "employee") return <PageSkeleton />;

  return (
    <RequireRole roles={["employee"]}>
      <PayslipList />
    </RequireRole>
  );
}
