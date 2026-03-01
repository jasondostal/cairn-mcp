"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { checkAuthStatus, getToken, fetchMe } from "@/lib/auth";

/**
 * Client-side auth guard (ca-124).
 *
 * When auth is disabled server-side, renders children immediately.
 * When auth is enabled, checks for valid token and redirects to /login if missing.
 * The /login page is always accessible without auth.
 */
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    // Login page is always accessible
    if (pathname === "/login") {
      setReady(true);
      return;
    }

    checkAuthStatus().then(async (status) => {
      if (!status.enabled) {
        // Auth disabled — everything works without tokens
        setReady(true);
        return;
      }

      const token = getToken();
      if (!token) {
        router.push("/login");
        return;
      }

      // Validate token is still good
      const user = await fetchMe();
      if (!user) {
        router.push("/login");
        return;
      }

      setReady(true);
    });
  }, [pathname, router]);

  if (!ready) return null;
  return <>{children}</>;
}
