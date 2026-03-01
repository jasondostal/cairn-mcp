/**
 * Client-side auth helpers (ca-124).
 *
 * Token stored in localStorage. When auth is disabled server-side,
 * getToken() returns null and all fetch calls work without auth headers.
 */

const TOKEN_KEY = "cairn_auth_token";
const USER_KEY = "cairn_auth_user";

export interface AuthUser {
  id: number;
  username: string;
  role: string;
  email?: string;
}

export interface AuthStatus {
  enabled: boolean;
  has_users: boolean;
}

// --- Token management ---

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function getUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function setUser(user: AuthUser): void {
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

// --- Auth headers ---

export function getAuthHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// --- Auth API calls ---

const BASE = "/api";

export async function checkAuthStatus(): Promise<AuthStatus> {
  const res = await fetch(`${BASE}/auth/status`);
  if (!res.ok) return { enabled: false, has_users: true };
  return res.json();
}

export async function login(
  username: string,
  password: string,
): Promise<{ access_token: string; user: AuthUser }> {
  const res = await fetch(`${BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Login failed" }));
    throw new Error(err.detail || "Login failed");
  }
  const data = await res.json();
  setToken(data.access_token);
  setUser(data.user);
  return data;
}

export async function register(
  username: string,
  password: string,
  email?: string,
): Promise<{ access_token: string; user: AuthUser }> {
  const res = await fetch(`${BASE}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password, email }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Registration failed" }));
    throw new Error(err.detail || "Registration failed");
  }
  const data = await res.json();
  setToken(data.access_token);
  setUser(data.user);
  return data;
}

export async function fetchMe(): Promise<AuthUser | null> {
  const token = getToken();
  if (!token) return null;
  const res = await fetch(`${BASE}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    if (res.status === 401) clearToken();
    return null;
  }
  const user = await res.json();
  setUser(user);
  return user;
}

export function logout(): void {
  clearToken();
  if (typeof window !== "undefined") {
    window.location.href = "/login";
  }
}
