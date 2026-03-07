/**
 * Auth primitives (ca-124).
 *
 * localStorage is the storage layer for JWT tokens and cached user data.
 * This module is the ONLY place that touches localStorage auth keys.
 * Components never call these directly — they use the AuthProvider context.
 *
 * The one exception is getAuthHeaders(), which api.ts calls to attach
 * Bearer tokens to requests. This is intentional — the fetch layer needs
 * headers without importing React context.
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
  oidc_enabled?: boolean;
  providers?: string[];
}

// ---------------------------------------------------------------------------
// localStorage access (module-private except getAuthHeaders)
// ---------------------------------------------------------------------------

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

function getStoredUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function setStoredUser(user: AuthUser): void {
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

function clearAuth(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

// ---------------------------------------------------------------------------
// Auth headers — used by api.ts fetch layer
// ---------------------------------------------------------------------------

export function getAuthHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------

const BASE = "/api";

export async function checkAuthStatus(): Promise<AuthStatus> {
  try {
    const res = await fetch(`${BASE}/auth/status`);
    if (!res.ok) return { enabled: false, has_users: true };
    return res.json();
  } catch {
    return { enabled: false, has_users: true };
  }
}

/** Login — stores token + user, returns user. Throws on failure. */
export async function loginApi(
  username: string,
  password: string,
): Promise<AuthUser> {
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
  setStoredUser(data.user);
  return data.user;
}

/** Register — stores token + user, returns user. Throws on failure. */
export async function registerApi(
  username: string,
  password: string,
  email?: string,
): Promise<AuthUser> {
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
  setStoredUser(data.user);
  return data.user;
}

/** Fetch current user from server. Updates localStorage cache. */
export async function fetchMe(): Promise<AuthUser | null> {
  const token = getToken();
  if (!token) return null;
  try {
    const res = await fetch(`${BASE}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) return null;
    const user = await res.json();
    setStoredUser(user);
    return user;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Auth lifecycle — called by AuthProvider only
// ---------------------------------------------------------------------------

/** Check if we have a token and try to resolve the user.
 *  Returns { token, user } or null if no valid session. */
export async function resolveSession(): Promise<{ user: AuthUser } | null> {
  const token = getToken();
  if (!token) return null;

  // Try localStorage cache first
  const cached = getStoredUser();
  if (cached) return { user: cached };

  // Cache miss — validate token against server
  const user = await fetchMe();
  if (!user) {
    // Token is invalid/expired
    clearAuth();
    return null;
  }
  return { user };
}

export function logout(): void {
  clearAuth();
}

/** Has a token in localStorage (quick sync check, no validation). */
export function hasToken(): boolean {
  return !!getToken();
}

/** Handle OIDC callback — exchanges one-time code for JWT via POST.
 *  Returns true if callback params were present (async exchange happens in background). */
export function handleOidcCallback(): boolean {
  if (typeof window === "undefined") return false;
  const params = new URLSearchParams(window.location.search);
  const oidcCode = params.get("oidc_code");
  // Legacy support: direct token param (will be removed in future)
  const legacyToken = params.get("token");
  if (!oidcCode && !legacyToken) return false;

  if (oidcCode) {
    // Exchange one-time code for JWT (avoids token exposure in URL/logs)
    fetch(`${BASE}/auth/oidc/exchange`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: oidcCode }),
    })
      .then((res) => {
        if (!res.ok) throw new Error("Code exchange failed");
        return res.json();
      })
      .then((data) => {
        setToken(data.access_token);
        setStoredUser({ id: 0, username: data.user.username, role: data.user.role });
        window.history.replaceState({}, "", window.location.pathname);
        window.location.href = "/";
      })
      .catch(() => {
        window.history.replaceState({}, "", window.location.pathname);
      });
  } else if (legacyToken) {
    const username = params.get("username");
    const role = params.get("role");
    if (username) {
      setToken(legacyToken);
      setStoredUser({ id: 0, username, role: role || "user" });
    }
    window.history.replaceState({}, "", window.location.pathname);
  }
  return true;
}
