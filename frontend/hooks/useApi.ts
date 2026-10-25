"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError, errorMessage } from "@/lib/api";

interface ApiState<T> {
  /** Which request the current `data`/`error` belong to (`null` until the first resolve). */
  path: string | null;
  nonce: number;
  data: T | undefined;
  error: ApiError | Error | undefined;
}

/**
 * Minimal data-fetching hook: loading / success / error + manual retry.
 * Pass `null` to pause the request (e.g. while a filter is still resolving).
 *
 * `loading`/`error` are derived from whether the stored state matches the
 * current request, so the effect only ever calls setState from async
 * callbacks (never synchronously in the effect body).
 */
export function useApi<T = unknown>(path: string | null) {
  const [state, setState] = useState<ApiState<T>>({
    path: null,
    nonce: 0,
    data: undefined,
    error: undefined,
  });
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (path === null) return;
    let cancelled = false;
    api<T>(path)
      .then((data) => {
        if (!cancelled) setState({ path, nonce, data, error: undefined });
      })
      .catch((err) => {
        if (!cancelled) setState({ path, nonce, data: undefined, error: err as Error });
      });
    return () => {
      cancelled = true;
    };
  }, [path, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  // `null` = paused: derive an empty result instead of storing it, so no
  // setState is needed in the effect just to clear state.
  if (path === null) {
    return {
      data: undefined,
      error: undefined,
      loading: false,
      reload,
      errorMessage: "",
    };
  }

  // Stale = no response for the current path + nonce has arrived yet.
  const stale = state.path !== path || state.nonce !== nonce;
  const error = stale ? undefined : state.error;
  return {
    data: state.data,
    error,
    loading: stale,
    reload,
    errorMessage: error ? errorMessage(error) : "",
  };
}
