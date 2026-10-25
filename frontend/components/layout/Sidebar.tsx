"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/components/auth/Auth";
import { Icon } from "./Icon";
import { NAV_ITEMS } from "./nav";
import { cx } from "@/lib/utils";
import { Badge } from "@/components/ui/Badge";

const ROLE_LABEL: Record<string, string> = {
  admin: "Administrator",
  hr: "HR",
  employee: "Employee",
};

function NavList({ collapsed, onNavigate }: { collapsed: boolean; onNavigate?: () => void }) {
  const { user } = useAuth();
  const pathname = usePathname();
  const items = NAV_ITEMS.filter((item) =>
    user ? item.roles.includes(user.role) : item.roles.includes("employee"),
  );

  return (
    <nav aria-label="Primary" className="flex-1 space-y-1 overflow-y-auto px-3 py-4">
      {items.map((item) => {
        const active =
          pathname === item.href || (item.href !== "/dashboard" && pathname.startsWith(`${item.href}/`));
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={onNavigate}
            title={collapsed ? item.label : undefined}
            aria-current={active ? "page" : undefined}
            className={cx(
              "group relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium",
              "transition-[background-color,color,box-shadow] duration-200 ease-snappy",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-bg",
              active
                ? "bg-accent/12 text-text shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] ring-1 ring-accent/30"
                : "text-muted hover:bg-surface-2 hover:text-text",
              collapsed && "justify-center px-2",
            )}
          >
            {active && !collapsed && (
              <span
                aria-hidden
                className="absolute -left-3 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-accent shadow-[0_0_12px_2px_rgba(231,183,90,0.45)]"
              />
            )}
            <Icon name={item.icon} className={cx("h-5 w-5 shrink-0", active ? "text-accent" : "text-muted group-hover:text-text")} />
            {!collapsed && <span className="truncate">{item.label}</span>}
          </Link>
        );
      })}
    </nav>
  );
}

function SidebarFooter({ collapsed }: { collapsed: boolean }) {
  const { user } = useAuth();
  if (!user || collapsed) return null;
  return (
    <div className="border-t border-border px-4 py-4">
      <p className="truncate text-sm font-medium text-text">{user.full_name}</p>
      <div className="mt-1.5 flex items-center gap-2">
        <Badge tone="accent">{ROLE_LABEL[user.role] ?? user.role}</Badge>
      </div>
    </div>
  );
}

export function Sidebar({
  collapsed,
  mobileOpen,
  onCloseMobile,
}: {
  collapsed: boolean;
  mobileOpen: boolean;
  onCloseMobile: () => void;
}) {
  return (
    <>
      {/* Desktop rail */}
      <aside
        className={cx(
          "fixed inset-y-0 left-0 z-40 hidden border-r border-border bg-surface",
          "transition-[width] duration-300 ease-snappy lg:flex lg:flex-col",
          "shadow-[inset_-1px_0_0_rgba(255,255,255,0.03)]",
          collapsed ? "w-[76px]" : "w-60",
        )}
      >
        <div className="flex h-16 items-center gap-2 border-b border-border px-4">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent text-sm font-bold text-accent-ink shadow-[var(--shadow-brass)]">
            H
          </div>
          {!collapsed && (
            <div className="leading-tight">
              <p className="text-sm font-semibold text-text">HCM Lite</p>
              <p className="text-[11px] text-muted">People operations</p>
            </div>
          )}
        </div>
        <NavList collapsed={collapsed} />
        <SidebarFooter collapsed={collapsed} />
      </aside>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="absolute inset-0 animate-fade bg-black/70 backdrop-blur-sm"
            onClick={onCloseMobile}
            aria-hidden
          />
          <aside className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] animate-drawer-in flex-col border-r border-border bg-surface shadow-[var(--shadow-pop)]">
            <div className="flex h-16 items-center justify-between border-b border-border px-4">
              <div className="flex items-center gap-2">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent text-sm font-bold text-accent-ink">
                  H
                </div>
                <p className="text-sm font-semibold text-text">HCM Lite</p>
              </div>
              <button
                onClick={onCloseMobile}
                aria-label="Close navigation"
                className="rounded-lg p-2 text-muted hover:bg-surface-2 hover:text-text"
              >
                <Icon name="x" />
              </button>
            </div>
            <NavList collapsed={false} onNavigate={onCloseMobile} />
            <SidebarFooter collapsed={false} />
          </aside>
        </div>
      )}
    </>
  );
}
