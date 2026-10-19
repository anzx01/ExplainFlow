import type { AuthResponse, AuthUser } from "./types";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8010";
const TOKEN_KEY = "explainflow_auth_token";

export function getSavedToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function saveToken(token: string): void {
  try {
    window.localStorage.setItem(TOKEN_KEY, token);
  } catch {
    /* localStorage 不可用时降级为仅会话内有效 */
  }
}

export function clearToken(): void {
  try {
    window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore */
  }
}

/** 统一带 Bearer token 的请求;非 2xx 时抛出含 detail 的错误 */
async function authRequest<T>(path: string, init?: RequestInit, token?: string | null): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const effective = token ?? getSavedToken();
  if (effective) headers["Authorization"] = `Bearer ${effective}`;
  const res = await fetch(`${BASE_URL}${path}`, { headers, ...init });
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body?.detail) detail = String(body.detail);
    } catch {
      /* keep status as message */
    }
    throw Object.assign(new Error(detail), { status: res.status });
  }
  return (await res.json()) as T;
}

export async function registerUser(username: string, password: string, displayName?: string): Promise<AuthResponse> {
  return authRequest<AuthResponse>("/auth/register", {
    method: "POST",
    body: JSON.stringify({ username, password, display_name: displayName || null }),
  });
}

export async function loginUser(username: string, password: string): Promise<AuthResponse> {
  return authRequest<AuthResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

/** 查询当前登录用户;401/网络错误返回 null 并清理失效 token */
export async function fetchCurrentUser(): Promise<AuthUser | null> {
  const token = getSavedToken();
  if (!token) return null;
  try {
    const data = await authRequest<{ user: AuthUser }>("/auth/me", { method: "GET" }, token);
    return data.user;
  } catch (err) {
    if ((err as { status?: number }).status === 401) clearToken();
    return null;
  }
}

export async function logoutUser(): Promise<void> {
  try {
    await authRequest("/auth/logout", { method: "POST" });
  } finally {
    clearToken();
  }
}
