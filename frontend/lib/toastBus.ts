/**
 * Tiny event bus so non-React code (`lib/api.ts`) can surface toasts without
 * importing React context. The `ToastProvider` subscribes on mount.
 */

export type ToastKind = "success" | "error" | "info";

export interface ToastInput {
  type: ToastKind;
  message: string;
}

type Listener = (toast: ToastInput) => void;

const listeners = new Set<Listener>();

export function emitToast(toast: ToastInput): void {
  listeners.forEach((listener) => {
    try {
      listener(toast);
    } catch {
      /* never let a toast break a request */
    }
  });
}

export function onToast(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
