"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { useAuth, RequireRole } from "@/components/auth/Auth";
import { PayrollRunDetail } from "@/features/payroll/PayrollFeature";
import { PageSkeleton } from "@/components/ui/Skeleton";

export default function PayrollRunPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { user } = useAuth();
  const id = Number(params?.id);

  useEffect(() => {
    if (!Number.isFinite(id) || id <= 0) router.replace("/payroll");
    else if (user && user.role === "employee") router.replace("/payslips");
  }, [id, user, router]);

  if (!Number.isFinite(id) || id <= 0 || (user && user.role === "employee")) {
    return <PageSkeleton />;
  }

  return (
    <RequireRole roles={["admin", "hr"]}>
      <PayrollRunDetail runId={id} />
    </RequireRole>
  );
}
