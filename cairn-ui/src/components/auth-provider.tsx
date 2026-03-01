"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  checkAuthStatus,
  resolveSession,
  logout as rawLogout,
  type AuthUser,
  type AuthStatus,
} from "@/lib/auth";

// ---------------------------------------------------------------------------
// Context shape
// ---------------------------------------------------------------------------

interface AuthContextValue {
  /** null = auth disabled or still loading. */
  user: AuthUser | null;
  /** Server-reported auth status. null while loading. */
  status: AuthStatus | null;
  /** True while the initial auth check is in progress. */
  loading: boolean;
  /** True when auth is enabled on the server. */
  authEnabled: boolean;
  /** Sign out and redirect to /login. */
  logout: () => void;
  /** Force-refresh user from server (e.g. after role change). */
  refreshUser: () => Promise<void>;
  /** Called by the fetch layer on 401 — clears state, redirects. */
  handleUnauthorized: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [loading, setLoading] = useState(true);

  const handleUnauthorized = useCallback(() => {
    rawLogout();
    setUser(null);
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      sessionStorage.setItem("cairn_return_to", window.location.pathname + window.location.search);
      router.push("/login");
    }
  }, [router]);

  const refreshUser = useCallback(async () => {
    const session = await resolveSession();
    setUser(session?.user ?? null);
  }, []);

  // Expose handleUnauthorized to the fetch layer via a global
  useEffect(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
(window as any).__cairn_on_401 = handleUnauthorized;
    return () => {
      delete // eslint-disable-next-line @typescript-eslint/no-explicit-any
(window as any).__cairn_on_401;
    };
  }, [handleUnauthorized]);

  // Boot: check auth status + resolve session
  useEffect(() => {
    let cancelled = false;

    async function boot() {
      const authStatus = await checkAuthStatus();
      if (cancelled) return;
      setStatus(authStatus);

      if (!authStatus.enabled) {
        // Auth disabled — no login required
        setLoading(false);
        return;
      }

      // Auth enabled — try to resolve existing session
      if (pathname === "/login") {
        // Don't resolve session on login page — let it handle its own flow
        setLoading(false);
        return;
      }

      const session = await resolveSession();
      if (cancelled) return;

      if (!session) {
        // No valid session — save intended destination, redirect to login
        if (typeof window !== "undefined" && pathname !== "/login") {
          sessionStorage.setItem("cairn_return_to", pathname + (window.location.search || ""));
        }
        setLoading(false);
        router.push("/login");
        return;
      }

      setUser(session.user);
      setLoading(false);
    }

    boot();
    return () => { cancelled = true; };
  }, [pathname, router]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      status,
      loading,
      authEnabled: status?.enabled ?? false,
      logout: handleUnauthorized,
      refreshUser,
      handleUnauthorized,
    }),
    [user, status, loading, handleUnauthorized, refreshUser],
  );

  // Show nothing while booting (prevents flash of wrong content)
  if (loading) return null;

  return (
    <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
  );
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}
