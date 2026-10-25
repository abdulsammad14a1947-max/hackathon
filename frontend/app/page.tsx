"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/** Role-neutral entry point: sends visitors to sign-in or their dashboard. */
export default function RootPage() {
  const router = useRouter();

  useEffect(() => {
    const token = typeof window !== "undefined" ? window.localStorage.getItem("hcm_token") : null;
    router.replace(token ? "/dashboard" : "/login");
  }, [router]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-accent border-t-transparent" />
    </div>
  );
}
