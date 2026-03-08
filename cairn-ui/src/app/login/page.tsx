"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { toast } from "sonner";
import { LogIn } from "lucide-react";
import Image from "next/image";
import {
  checkAuthStatus,
  loginApi,
  registerApi,
  hasToken,
  handleOidcCallback,
  type AuthStatus,
} from "@/lib/auth";
import { api } from "@/lib/api";

function getReturnUrl(): string {
  if (typeof window === "undefined") return "/";
  const stored = sessionStorage.getItem("cairn_return_to");
  sessionStorage.removeItem("cairn_return_to");
  if (stored && stored !== "/login" && stored !== "/login/") return stored;
  return "/";
}

export default function LoginPage() {
  const router = useRouter();
  const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null);
  const [isRegister, setIsRegister] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [oidcLoading, setOidcLoading] = useState(false);

  useEffect(() => {
    async function boot() {
      // Handle OIDC callback (?oidc_code=...)
      if (await handleOidcCallback()) {
        // Hard redirect — bypasses AuthProvider's stale boot state
        window.location.href = getReturnUrl();
        return;
      }

      // If already logged in, redirect
      if (hasToken()) {
        router.push(getReturnUrl());
        return;
      }
      const status = await checkAuthStatus();
      setAuthStatus(status);
      // If auth not enabled, redirect to main app
      if (!status.enabled) {
        router.push("/");
        return;
      }
      // If no users yet, show register form
      if (!status.has_users) {
        setIsRegister(true);
      }
    }
    boot();
  }, [router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      if (isRegister) {
        await registerApi(username, password, email || undefined);
        toast.success("Account created");
      } else {
        await loginApi(username, password);
        toast.success("Logged in");
      }
      router.push(getReturnUrl());
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setLoading(false);
    }
  };

  const handleOidcLogin = async () => {
    setOidcLoading(true);
    try {
      const callbackUrl = `${window.location.origin}/api/auth/oidc/callback`;
      const result = await api.authOidcLogin(callbackUrl);
      window.location.href = result.authorization_url;
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "SSO login failed");
      setOidcLoading(false);
    }
  };

  if (authStatus === null) return null;
  if (!authStatus.enabled) return null;

  const showOidc = authStatus.oidc_enabled;

  return (
    <div className="flex min-h-dvh items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="items-center">
          <Image
            src="/cairn-mark-trail.svg"
            alt="Cairn"
            width={64}
            height={64}
            className="mb-2 dark:invert"
            priority
          />
          <CardTitle className="text-center">
            {isRegister
              ? authStatus.has_users
                ? "Create Account"
                : "Setup Admin Account"
              : "Sign In"}
          </CardTitle>
          {!authStatus.has_users && isRegister && (
            <p className="text-sm text-muted-foreground">
              First user becomes the admin.
            </p>
          )}
        </CardHeader>
        <CardContent>
          {showOidc && !isRegister && (
            <>
              <Button
                variant="outline"
                className="w-full"
                onClick={handleOidcLogin}
                disabled={oidcLoading}
              >
                <LogIn className="mr-2 h-4 w-4" />
                {oidcLoading ? "Redirecting..." : "Sign in with SSO"}
              </Button>
              <div className="relative my-4">
                <div className="absolute inset-0 flex items-center">
                  <span className="w-full border-t" />
                </div>
                <div className="relative flex justify-center text-xs uppercase">
                  <span className="bg-card px-2 text-muted-foreground">or</span>
                </div>
              </div>
            </>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1">
              <label htmlFor="login-username" className="text-xs font-medium text-muted-foreground uppercase">
                Username
              </label>
              <Input
                id="login-username"
                placeholder="Username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                autoFocus={!showOidc}
              />
            </div>
            {isRegister && (
              <div className="space-y-1">
                <label htmlFor="login-email" className="text-xs font-medium text-muted-foreground uppercase">
                  Email (optional)
                </label>
                <Input
                  id="login-email"
                  type="email"
                  placeholder="Email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
            )}
            <div className="space-y-1">
              <label htmlFor="login-password" className="text-xs font-medium text-muted-foreground uppercase">
                Password
              </label>
              <Input
                id="login-password"
                type="password"
                placeholder="Password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={6}
              />
            </div>
            <Button type="submit" className="w-full" disabled={loading}>
              {loading
                ? "..."
                : isRegister
                  ? "Create Account"
                  : "Sign In"}
            </Button>
          </form>

          {authStatus.has_users && (
            <button
              type="button"
              className="mt-4 w-full text-center text-sm text-muted-foreground hover:text-foreground"
              onClick={() => setIsRegister(!isRegister)}
            >
              {isRegister
                ? "Already have an account? Sign in"
                : "Need an account? Register"}
            </button>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
