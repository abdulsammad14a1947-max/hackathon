import { apiUrl } from "./config";
import { clearSession, getToken } from "./auth";
import { emitToast } from "./toastBus";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  fieldErrors: Record<string, string>;

  constructor(
    status: number,
    message: string,
    detail: unknown = undefined,
    fieldErrors: Record<string, string> = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.fieldErrors = fieldErrors;
  }
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  formData?: FormData;
  headers?: Record<string, string>;
  signal?: AbortSignal;
  timeoutMs?: number;
}

const PUBLIC_PATHS = ["/login", "/setup"];

function isPublicPath(): boolean {
  if (typeof window === "undefined") return false;
  return PUBLIC_PATHS.some((p) => window.location.pathname.startsWith(p));
}

/** Extracts `{field: message}` from a FastAPI 422 `detail` list. */
function extractFieldErrors(detail: unknown): Record<string, string> {
  const out: Record<string, string> = {};
  if (Array.isArray(detail)) {
    for (const item of detail) {
      if (item && typeof item === "object") {
        const o = item as Record<string, unknown>;
        const loc = Array.isArray(o.loc) ? o.loc.map(String) : [];
        const key = loc.length > 1 ? loc.slice(1).join(".") : loc.join(".");
        if (key) out[key] = String(o.msg ?? "Invalid value");
      }
    }
  }
  return out;
}

function detailToMessage(detail: unknown, fallback: string): string {
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const first = detail[0];
    if (first && typeof first === "object") {
      const o = first as Record<string, unknown>;
      if (typeof o.msg === "string") return o.msg;
    }
    if (typeof first === "string") return first;
  }
  if (detail && typeof detail === "object") {
    const o = detail as Record<string, unknown>;
    if (typeof o.detail === "string") return o.detail;
    if (typeof o.message === "string") return o.message;
  }
  return fallback;
}

async function buildError(response: Response, fallback: string): Promise<ApiError> {
  let detail: unknown;
  try {
    const text = await response.text();
    if (text) {
      try {
        detail = JSON.parse(text);
      } catch {
        detail = text;
      }
    }
  } catch {
    detail = undefined;
  }

  const status = response.status;
  let message = fallback;
  if (status === 401) message = "Your session has expired. Please sign in again.";
  else if (status === 403) message = "You don't have permission to perform this action.";
  else if (status === 404) message = "The requested record was not found.";
  else if (status === 409) message = detailToMessage(detail, "This conflicts with existing data.");
  else if (status === 429)
    message = detailToMessage(detail, "Too many requests — please wait a moment and try again.");
  else message = detailToMessage(detail, fallback);

  return new ApiError(status, message, detail, extractFieldErrors(detail));
}

async function rawRequest(path: string, options: RequestOptions): Promise<Response> {
  const headers: Record<string, string> = { Accept: "application/json", ...options.headers };
  const init: RequestInit = { method: options.method ?? "GET", headers, credentials: "omit" };

  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  if (options.formData) {
    init.body = options.formData;
    // let the browser set the multipart boundary
  } else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(options.body);
  }

  const controller = new AbortController();
  const timer = options.timeoutMs
    ? setTimeout(() => controller.abort(new Error("timeout")), options.timeoutMs)
    : null;
  if (options.signal) {
    if (options.signal.aborted) controller.abort();
    else options.signal.addEventListener("abort", () => controller.abort(), { once: true });
  }
  init.signal = controller.signal;

  try {
    return await fetch(apiUrl(path), init);
  } catch (err) {
    if (options.signal?.aborted) throw err;
    if (controller.signal.aborted) {
      throw new ApiError(0, "The request timed out. Please try again.");
    }
    throw new ApiError(
      0,
      "Cannot reach the HCM Lite API. Check that the backend is running and try again.",
    );
  } finally {
    if (timer) clearTimeout(timer);
  }
}

/** JSON request helper. Throws `ApiError` on any non-2xx response. */
export async function api<T = unknown>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await rawRequest(path, options);
  if (response.ok) {
    if (response.status === 204) return undefined as T;
    const text = await response.text();
    if (!text) return undefined as T;
    try {
      return JSON.parse(text) as T;
    } catch {
      return text as unknown as T;
    }
  }

  const error = await buildError(response, "Request failed. Please try again.");

  if (error.status === 401) {
    clearSession();
    if (!isPublicPath() && typeof window !== "undefined") {
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- full reload intentionally clears token, caches and toasts on session expiry
      window.location.assign("/login");
    }
    throw error;
  }

  if (error.status === 403) {
    emitToast({ type: "error", message: error.message });
  }

  throw error;
}

/** Authenticated binary download (CSV export, payslip PDF). */
export async function apiBlob(path: string, options: RequestOptions = {}): Promise<Response> {
  const response = await rawRequest(path, { ...options, timeoutMs: options.timeoutMs ?? 30000 });
  if (response.ok) return response;
  const error = await buildError(response, "Download failed.");
  if (error.status === 401) {
    clearSession();
    if (!isPublicPath() && typeof window !== "undefined") {
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- full reload intentionally clears token, caches and toasts on session expiry
      window.location.assign("/login");
    }
  }
  if (error.status === 403) {
    emitToast({ type: "error", message: error.message });
  }
  throw error;
}

/** Triggers a browser download from an authenticated binary response. */
export async function downloadFile(path: string, filename: string): Promise<void> {
  const response = await apiBlob(path);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error && err.message) return err.message;
  return "Something went wrong. Please try again.";
}

export function isTimeout(err: unknown): boolean {
  return err instanceof Error && /timeout/i.test(err.message);
}
