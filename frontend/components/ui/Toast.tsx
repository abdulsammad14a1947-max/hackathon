"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { onToast, type ToastInput, type ToastKind } from "@/lib/toastBus";
import { cx } from "@/lib/utils";

interface ToastItem extends ToastInput {
  id: number;
}

const ToastContext = createContext<(toast: ToastInput) => void>(() => {});

export function useToast() {
  return useContext(ToastContext);
}

const TONE: Record<ToastKind, string> = {
  success: "border-success/50 text-success",
  error: "border-danger/50 text-danger",
  info: "border-info/50 text-info",
};

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const counter = useRef(0);

  const push = useCallback((toast: ToastInput) => {
    const id = ++counter.current;
    setToasts((prev) => [...prev, { ...toast, id }].slice(-4));
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 5000);
  }, []);

  useEffect(() => onToast(push), [push]);

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div
        aria-live="polite"
        aria-atomic="false"
        className="pointer-events-none fixed right-4 top-4 z-[100] flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-2"
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            role="status"
            className={cx(
              "pointer-events-auto animate-toast-in rounded-lg border bg-surface-2 px-4 py-3 text-sm shadow-[var(--shadow-pop)]",
              TONE[t.type] ?? TONE.info,
            )}
          >
            <span className="text-text/90">{t.message}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
