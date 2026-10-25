import { Suspense } from "react";
import { AuthGate } from "@/components/auth/Auth";
import { PageSkeleton } from "@/components/ui/Skeleton";

/**
 * `AuthGate`/`Header` read `usePathname()`, which cannot be resolved while
 * prerendering dynamic routes — Suspense lets the build render a fallback.
 */
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={<div className="p-6"><PageSkeleton /></div>}>
      <AuthGate>{children}</AuthGate>
    </Suspense>
  );
}
