"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { useAuth } from "@/components/auth/Auth";
import { EmployeeProfile } from "@/features/employees/EmployeeProfile";
import { PageSkeleton } from "@/components/ui/Skeleton";

export default function EmployeeDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { user } = useAuth();
  const id = Number(params?.id);

  const isSelf = Boolean(user?.employee_id && Number(user.employee_id) === id);
  const isStaff = user?.role === "admin" || user?.role === "hr";

  useEffect(() => {
    if (!Number.isFinite(id) || id <= 0) {
      router.replace("/employees");
      return;
    }
    // Employees may only open their own profile; the server enforces this too.
    if (user && !isStaff && !isSelf) {
      router.replace(user.employee_id ? `/employees/${user.employee_id}` : "/dashboard");
    }
  }, [id, isStaff, isSelf, router, user]);

  if (!Number.isFinite(id) || id <= 0) return <PageSkeleton />;
  if (user && !isStaff && !isSelf) return <PageSkeleton />;

  // Brief matrix #06: HR edits employee records; Admin is view-only on this page.
  const editMode: "full" | "contact" | "none" = isStaff
    ? user?.role === "hr"
      ? "full"
      : "none"
    : isSelf
      ? "contact"
      : "none";

  return <EmployeeProfile employeeId={id} isSelf={isSelf} editMode={editMode} />;
}
