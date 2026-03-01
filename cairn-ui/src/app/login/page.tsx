"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { toast } from "sonner";
import {
  checkAuthStatus,
  login,
  register,
  getToken,
  type AuthStatus,
} from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null);
  const [isRegister, setIsRegister] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // If already logged in, redirect
    if (getToken()) {
      router.push("/");
      return;
    }
    checkAuthStatus().then((status) => {
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
    });
  }, [router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      if (isRegister) {
        await register(username, password, email || undefined);
        toast.success("Account created");
      } else {
        await login(username, password);
        toast.success("Logged in");
      }
      router.push("/");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setLoading(false);
    }
  };

  if (authStatus === null) return null;
  if (!authStatus.enabled) return null;

  return (
    <div className="flex min-h-dvh items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>
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
          <form onSubmit={handleSubmit} className="space-y-4">
            <Input
              placeholder="Username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoFocus
            />
            {isRegister && (
              <Input
                type="email"
                placeholder="Email (optional)"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            )}
            <Input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={6}
            />
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
