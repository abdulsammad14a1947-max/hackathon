"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";
import { cx } from "@/lib/utils";

const COLLAPSE_KEY = "hcm_sidebar_collapsed";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  /* eslint-disable react-hooks/set-state-in-effect -- one-time read of the persisted
     sidebar preference after mount: localStorage is unavailable during SSR/prerender,
     so a lazy useState initialiser would cause a hydration mismatch. */
  useEffect(() => {
    try {
      setCollapsed(window.localStorage.getItem(COLLAPSE_KEY) === "1");
    } catch {
      /* ignore */
    }
  }, []);
  /* eslint-enable react-hooks/set-state-in-effect */

  const toggle = () => {
    setCollapsed((c) => {
      const next = !c;
      try {
        window.localStorage.setItem(COLLAPSE_KEY, next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });
  };

  return (
    <div className="min-h-screen bg-bg">
      <Sidebar
        collapsed={collapsed}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
      />
      <div
        className={cx(
          "flex min-h-screen flex-col transition-[padding] duration-200",
          collapsed ? "lg:pl-[76px]" : "lg:pl-60",
        )}
      >
        <Header
          onToggleSidebar={toggle}
          onOpenMobileNav={() => setMobileOpen(true)}
        />
        <main
          key={pathname}
          className="mx-auto w-full max-w-[1600px] flex-1 animate-rise-sm px-4 py-6 sm:px-6 lg:px-8"
        >
          {children}
        </main>
        <footer className="border-t border-border px-4 py-4 text-center text-[11px] tracking-wide text-muted/70 sm:px-6">
          HCM Lite — demo build. Data shown is served by the live API.
        </footer>
      </div>
    </div>
  );
}
