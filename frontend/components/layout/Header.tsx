"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/components/auth/Auth";
import { api } from "@/lib/api";
import { Icon } from "./Icon";
import { pageTitle } from "./nav";
import { NotificationBell } from "./NotificationBell";
import { cx } from "@/lib/utils";
import { Badge } from "@/components/ui/Badge";

const ROLE_LABEL: Record<string, string> = {
  admin: "Administrator",
  hr: "HR",
  employee: "Employee",
};

function useApiHealth() {
  const [status, setStatus] = useState<"checking" | "online" | "offline">("checking");
  useEffect(() => {
    let cancelled = false;
    const check = () => {
      api("/api/health", { timeoutMs: 5000 })
        .then(() => !cancelled && setStatus("online"))
        .catch(() => !cancelled && setStatus("offline"));
    };
    check();
    const timer = setInterval(check, 60_000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);
  return status;
}

function UserMenu() {
  const { user, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!user) return null;

  const initials = user.full_name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="menu"
        className="flex items-center gap-2 rounded-lg p-1.5 transition-colors hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      >
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-accent/20 text-xs font-semibold text-accent ring-1 ring-accent/40">
          {initials || "?"}
        </span>
        <span className="hidden text-left sm:block">
          <span className="block max-w-[10rem] truncate text-sm font-medium text-text">
            {user.full_name}
          </span>
          <span className="block text-[11px] text-muted">{ROLE_LABEL[user.role] ?? user.role}</span>
        </span>
        <Icon name="chevronDown" className="hidden h-4 w-4 text-muted sm:block" />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 z-50 mt-2 w-60 animate-pop overflow-hidden rounded-xl border border-border bg-surface shadow-[var(--shadow-pop)]"
        >
          <div className="border-b border-border px-4 py-3">
            <p className="truncate text-sm font-medium text-text">{user.full_name}</p>
            <p className="truncate text-xs text-muted">{user.email}</p>
            <div className="mt-2">
              <Badge tone="accent">{ROLE_LABEL[user.role] ?? user.role}</Badge>
            </div>
          </div>
          <div className="p-1.5">
            <Link
              href="/change-password"
              role="menuitem"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-muted transition-colors hover:bg-surface-2 hover:text-text"
            >
              <Icon name="key" className="h-4 w-4" /> Change password
            </Link>
            <button
              role="menuitem"
              onClick={() => {
                setOpen(false);
                signOut();
              }}
              className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-muted transition-colors hover:bg-surface-2 hover:text-danger"
            >
              <Icon name="logout" className="h-4 w-4" /> Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export function Header({
  onToggleSidebar,
  onOpenMobileNav,
}: {
  onToggleSidebar: () => void;
  onOpenMobileNav: () => void;
}) {
  const pathname = usePathname();
  const health = useApiHealth();

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-2 border-b border-border/80 bg-surface/85 px-4 backdrop-blur-md sm:px-6">
      <button
        type="button"
        onClick={onOpenMobileNav}
        aria-label="Open navigation"
        className="rounded-lg p-2 text-muted transition-[background-color,color] duration-200 ease-snappy hover:bg-surface-2 hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent lg:hidden"
      >
        <Icon name="menu" />
      </button>
      <button
        type="button"
        onClick={onToggleSidebar}
        aria-label="Collapse sidebar"
        className="hidden rounded-lg p-2 text-muted transition-[background-color,color] duration-200 ease-snappy hover:bg-surface-2 hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent lg:block"
      >
        <Icon name="menu" />
      </button>

      <h1 className="ml-1 truncate text-base font-semibold tracking-tight text-text sm:text-lg">
        {pageTitle(pathname)}
      </h1>
      <span aria-hidden className="ml-2 hidden h-4 w-px bg-border sm:block" />

      <div className="ml-auto flex items-center gap-1.5 sm:gap-3">
        <span
          title={health === "online" ? "API connected" : "API unreachable"}
          className="hidden items-center gap-1.5 rounded-full border border-border bg-surface-2 px-2.5 py-1 text-[11px] text-muted sm:flex"
        >
          <span
            className={cx(
              "h-1.5 w-1.5 rounded-full",
              health === "online" && "bg-success",
              health === "offline" && "bg-danger",
              health === "checking" && "animate-pulse bg-warning",
            )}
          />
          {health === "online" ? "API online" : health === "offline" ? "API offline" : "Checking…"}
        </span>
        <NotificationBell />
        <UserMenu />
      </div>
    </header>
  );
}
