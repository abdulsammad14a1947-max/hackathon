"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, errorMessage } from "@/lib/api";
import { asPage, isObject, toNum, cx } from "@/lib/utils";
import { fmtDateTime } from "@/lib/format";
import { Icon } from "./Icon";
import type { Notification } from "@/types/api";

function parseCount(payload: unknown): number {
  if (typeof payload === "number") return payload;
  if (isObject(payload)) {
    if (typeof payload.count === "number") return payload.count;
    if (typeof payload.unread_count === "number") return payload.unread_count;
    if (Array.isArray(payload.items)) return toNum(payload.unread_count, payload.items.length);
    const asPageObj = payload as Record<string, unknown>;
    if (typeof asPageObj.total === "number") return asPageObj.total;
  }
  return 0;
}

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [marking, setMarking] = useState(false);
  const [list, setList] = useState<Notification[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [count, setCount] = useState<number | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const router = useRouter();

  const refreshCount = useCallback(() => {
    api<unknown>("/api/notifications/unread-count")
      .then((payload) => setCount(parseCount(payload)))
      .catch(() => setCount((c) => c));
  }, []);

  useEffect(() => {
    refreshCount();
    const timer = setInterval(refreshCount, 60_000);
    return () => clearInterval(timer);
  }, [refreshCount]);

  useEffect(() => {
    if (!open) return;
    api<unknown>("/api/notifications")
      .then((payload) => {
        setList(asPage<Notification>(payload).items);
        setListError(null);
      })
      .catch((err) => setListError(errorMessage(err)));
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const unreadIds = (list ?? []).filter((n) => !n.is_read).map((n) => n.id);

  const markAllRead = async () => {
    const ids = unreadIds.length ? unreadIds : (list ?? []).map((n) => n.id);
    if (!ids.length) return;
    setMarking(true);
    try {
      await api("/api/notifications/read", { method: "POST", body: { ids } });
      setList((prev) => (prev ? prev.map((n) => ({ ...n, is_read: true })) : prev));
      setCount(0);
    } catch (err) {
      setListError(errorMessage(err));
    } finally {
      setMarking(false);
    }
  };

  const openItem = async (item: Notification) => {
    if (!item.is_read) {
      try {
        await api("/api/notifications/read", { method: "POST", body: { ids: [item.id] } });
        setList((prev) =>
          prev ? prev.map((n) => (n.id === item.id ? { ...n, is_read: true } : n)) : prev,
        );
        setCount((c) => Math.max(0, (c ?? 1) - 1));
      } catch {
        /* notification stays unread — non-fatal */
      }
    }
    setOpen(false);
    if (item.link) router.push(item.link);
  };

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label={
          count && count > 0 ? `Notifications, ${count} unread` : "Notifications"
        }
        aria-expanded={open}
        className="relative rounded-lg p-2 text-muted transition-colors hover:bg-surface-2 hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      >
        <Icon name="bell" />
        {count !== null && count > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[10px] font-bold leading-none text-white">
            {count > 9 ? "9+" : count}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 z-50 mt-2 w-[min(22rem,calc(100vw-2rem))] animate-pop overflow-hidden rounded-xl border border-border bg-surface shadow-[var(--shadow-pop)]">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <p className="text-sm font-semibold text-text">Notifications</p>
            <button
              onClick={markAllRead}
              disabled={marking || (list?.length ?? 0) === 0}
              className="text-xs font-medium text-accent hover:text-accent-hover disabled:opacity-50"
            >
              Mark all read
            </button>
          </div>
          <div className="max-h-80 overflow-y-auto">
            {!list && !listError && (
              <div className="space-y-2 p-4" aria-hidden>
                {[0, 1, 2].map((i) => (
                  <div key={i} className="h-10 animate-pulse rounded bg-surface-2" />
                ))}
              </div>
            )}
            {listError && <p className="p-4 text-xs text-danger">{listError}</p>}
            {list && list.length === 0 && (
              <p className="p-6 text-center text-xs text-muted">You&apos;re all caught up.</p>
            )}
            {list?.map((n) => (
              <button
                key={n.id}
                onClick={() => openItem(n)}
                className={cx(
                  "block w-full border-b border-border px-4 py-3 text-left transition-colors last:border-b-0 hover:bg-surface-2",
                  !n.is_read && "bg-accent/5",
                )}
              >
                <span className="flex items-start gap-2">
                  {!n.is_read && <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />}
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-text">{n.title}</span>
                    {n.body && <span className="mt-0.5 block text-xs text-muted">{n.body}</span>}
                    <span className="mt-1 block text-[11px] text-muted/70">
                      {fmtDateTime(n.created_at)}
                    </span>
                  </span>
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
