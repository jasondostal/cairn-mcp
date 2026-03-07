"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { UserCog, LogOut } from "lucide-react";
import Link from "next/link";
import { useAuth } from "@/components/auth-provider";

export function AuthUserCard() {
  const { user, authEnabled, logout } = useAuth();
  if (!authEnabled || !user) return null;
  return (
    <Card className="mb-4">
      <CardContent className="flex items-center justify-between py-3">
        <div className="flex items-center gap-3 text-sm">
          <UserCog className="h-4 w-4 text-muted-foreground" />
          <span>Signed in as <strong>{user.username}</strong></span>
          <Badge variant={user.role === "admin" ? "destructive" : "secondary"}>
            {user.role}
          </Badge>
        </div>
        <div className="flex items-center gap-2">
          {user.role === "admin" && (
            <Link href="/admin/users">
              <Button variant="outline" size="sm">Manage Users</Button>
            </Link>
          )}
          <Button variant="ghost" size="sm" onClick={logout}>
            <LogOut className="mr-1 h-3 w-3" /> Sign Out
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
