"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { useAuth, RequireRole } from "@/components/auth/Auth";
import { PayslipViewer } from "@/features/payroll/Payslips";
import { PageSkeleton } from "@/components/ui/Skeleton";

export default function PayslipDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { user } = useAuth();
  const id = Number(params?.id);

  useEffect(() => {
    if (!Number.isFinite(id) || id <= 0) router.replace("/payslips");
    else if (user && user.role !== "employee") router.replace("/payroll");
  }, [id, user, router]);

  if (!Number.isFinite(id) || id <= 0 || (user && user.role !== "employee")) {
    return <PageSkeleton />;
  }

  return (
    <RequireRole roles={["employee"]}>
      <PayslipViewer itemId={id} />
    </RequireRole>
  );
}
