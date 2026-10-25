import type { User } from "@/types/api";

const TOKEN_KEY = "hcm_token";
const USER_KEY = "hcm_user";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function getUser(): User | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(USER_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as User;
    if (!parsed || typeof parsed.id !== "number") return null;
    return parsed;
  } catch {
    return null;
  }
}

export function setSession(token: string, user: User): void {
  window.localStorage.setItem(TOKEN_KEY, token);
  window.localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function updateUser(patch: Partial<User>): User | null {
  const user = getUser();
  if (!user) return null;
  const next = { ...user, ...patch };
  window.localStorage.setItem(USER_KEY, JSON.stringify(next));
  return next;
}

export function clearSession(): void {
  try {
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem(USER_KEY);
  } catch {
    /* ignore */
  }
}

export function isAuthenticated(): boolean {
  return Boolean(getToken());
}
