"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { clearSession, getToken, getUser, updateUser } from "@/lib/auth";
import { api } from "@/lib/api";
import type { Role, User } from "@/types/api";
import { AppShell } from "@/components/layout/AppShell";
import { PageSkeleton } from "@/components/ui/Skeleton";

interface AuthValue {
  user: User | null;
  ready: boolean;
  setUser: (user: User) => void;
  signOut: () => void;
}

const AuthContext = createContext<AuthValue>({
  user: null,
  ready: false,
  setUser: () => {},
  signOut: () => {},
});

export function useAuth() {
  return useContext(AuthContext);
}

export function AuthGate({ children }: { children: React.ReactNode }) {
  const [user, setUserState] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const router = useRouter();
  const pathname = usePathname();

  /* eslint-disable react-hooks/set-state-in-effect -- one-time read of the locally
     stored session after mount: localStorage is unavailable during SSR/prerender,
     so this cannot be a lazy useState initialiser without a hydration mismatch. */
  useEffect(() => {
    const token = getToken();
    const stored = getUser();
    if (!token || !stored) {
      setUserState(null);
      setReady(true);
      router.replace("/login");
      return;
    }
    setUserState(stored);
    setReady(true);
    if (stored.must_change_password && !pathname.startsWith("/change-password")) {
      router.replace("/change-password");
    }
  }, [pathname, router]);
  /* eslint-enable react-hooks/set-state-in-effect */

  const setUser = useCallback((next: User) => setUserState(next), []);

  const signOut = useCallback(() => {
    const token = getToken();
    if (token) {
      api("/api/auth/logout", { method: "POST" }).catch(() => {
        /* best effort — local sign-out always proceeds */
      });
    }
    clearSession();
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- full reload on sign-out intentionally clears all in-memory client state
    window.location.assign("/login");
  }, []);

  if (!ready) {
    return (
      <div className="min-h-screen bg-bg">
        <PageSkeleton />
      </div>
    );
  }

  if (!user) return null;

  // Block the entire app until the forced password change is completed.
  if (user.must_change_password && !pathname.startsWith("/change-password")) {
    return (
      <div className="min-h-screen bg-bg" aria-busy="true">
        <PageSkeleton />
      </div>
    );
  }

  return (
    <AuthContext.Provider value={{ user, ready, setUser, signOut }}>
      <AppShell>{children}</AppShell>
    </AuthContext.Provider>
  );
}

/** Blocks a route from a role that may not access it and returns to /dashboard. */
export function RequireRole({
  roles,
  children,
}: {
  roles: Role[];
  children: React.ReactNode;
}) {
  const { user, ready } = useAuth();
  const router = useRouter();

  const allowed = ready && !!user && roles.includes(user.role);

  useEffect(() => {
    if (ready && user && !roles.includes(user.role)) {
      router.replace("/dashboard");
    }
  }, [ready, user, roles, router]);

  if (!allowed) return <PageSkeleton />;
  return <>{children}</>;
}

/** Updates the persisted user after e.g. a password change. */
export function useUpdateSessionUser() {
  return useCallback((patch: Partial<User>) => updateUser(patch), []);
}
