"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { SingleSelect } from "@/components/ui/single-select";
import { PageLayout } from "@/components/page-layout";
import { SkeletonList } from "@/components/skeleton-list";
import { toast } from "sonner";
import { getAuthHeaders, getUser, checkAuthStatus } from "@/lib/auth";
import { Plus, UserCog, Shield } from "lucide-react";

interface User {
  id: number;
  username: string;
  email: string | null;
  role: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

const BASE = "/api";

function DisabledState() {
  return (
    <PageLayout title="Users" icon={UserCog}>
      <div className="flex flex-col items-center justify-center h-full text-center max-w-lg mx-auto gap-6 p-8">
        <div className="rounded-full bg-muted p-4">
          <Shield className="h-8 w-8 text-muted-foreground" />
        </div>
        <div>
          <h2 className="text-xl font-semibold mb-2">Authentication not enabled</h2>
          <p className="text-sm text-muted-foreground mb-4">
            Enable multi-user authentication by setting the <code className="text-xs bg-muted px-1.5 py-0.5 rounded">CAIRN_AUTH_ENABLED=true</code> and <code className="text-xs bg-muted px-1.5 py-0.5 rounded">CAIRN_AUTH_JWT_SECRET</code> environment variables.
          </p>
        </div>
        <div className="text-left w-full space-y-4">
          <div>
            <h3 className="text-sm font-medium mb-1">Quick start</h3>
            <pre className="text-xs bg-muted rounded p-3 overflow-x-auto">
{`CAIRN_AUTH_ENABLED=true
CAIRN_AUTH_JWT_SECRET=your-secret-key-here`}
            </pre>
          </div>
          <p className="text-xs text-muted-foreground">
            The first user to register will automatically become the admin.
            Agent accounts can be created from this page after setup.
          </p>
        </div>
      </div>
    </PageLayout>
  );
}

export default function AdminUsersPage() {
  const router = useRouter();
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [authDisabled, setAuthDisabled] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newRole, setNewRole] = useState("user");

  const currentUser = getUser();

  const fetchUsers = useCallback(async () => {
    try {
      const res = await fetch(`${BASE}/auth/users`, {
        headers: getAuthHeaders(),
      });
      if (res.status === 403) {
        router.push("/");
        return;
      }
      if (!res.ok) throw new Error("Failed to fetch users");
      const data = await res.json();
      setUsers(data.items || []);
    } catch {
      toast.error("Failed to load users");
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    async function init() {
      const status = await checkAuthStatus();
      if (!status.enabled) {
        setAuthDisabled(true);
        setLoading(false);
        return;
      }
      if (!currentUser || currentUser.role !== "admin") {
        router.push("/");
        return;
      }
      fetchUsers();
    }
    init();
  }, [currentUser, router, fetchUsers]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await fetch(`${BASE}/auth/users`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({
          username: newUsername,
          password: newPassword,
          email: newEmail || null,
          role: newRole,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to create user");
      }
      toast.success(`User ${newUsername} created`);
      setShowCreate(false);
      setNewUsername("");
      setNewPassword("");
      setNewEmail("");
      setNewRole("user");
      fetchUsers();
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to create user");
    }
  };

  const toggleActive = async (user: User) => {
    try {
      const res = await fetch(`${BASE}/auth/users/${user.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({ is_active: !user.is_active }),
      });
      if (!res.ok) throw new Error("Failed to update user");
      toast.success(`${user.username} ${user.is_active ? "deactivated" : "activated"}`);
      fetchUsers();
    } catch {
      toast.error("Failed to update user");
    }
  };

  const changeRole = async (user: User, role: string) => {
    try {
      const res = await fetch(`${BASE}/auth/users/${user.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({ role }),
      });
      if (!res.ok) throw new Error("Failed to update role");
      toast.success(`${user.username} role changed to ${role}`);
      fetchUsers();
    } catch {
      toast.error("Failed to update role");
    }
  };

  const roleColor = (role: string) => {
    if (role === "admin") return "destructive" as const;
    if (role === "agent") return "secondary" as const;
    return "default" as const;
  };

  if (loading) {
    return (
      <PageLayout title="Users" icon={UserCog}>
        <SkeletonList count={3} />
      </PageLayout>
    );
  }

  if (authDisabled) {
    return <DisabledState />;
  }

  return (
    <PageLayout title="Users" icon={UserCog}>
      <div className="space-y-4">
        <div className="flex justify-end">
          <Button size="sm" onClick={() => setShowCreate(!showCreate)}>
            <Plus className="mr-1 h-4 w-4" /> Create User
          </Button>
        </div>

        {showCreate && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Create User</CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleCreate} className="flex flex-wrap gap-3 items-end">
                <Input
                  placeholder="Username"
                  value={newUsername}
                  onChange={(e) => setNewUsername(e.target.value)}
                  required
                  className="w-40"
                />
                <Input
                  type="password"
                  placeholder="Password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  required
                  minLength={6}
                  className="w-40"
                />
                <Input
                  type="email"
                  placeholder="Email"
                  value={newEmail}
                  onChange={(e) => setNewEmail(e.target.value)}
                  className="w-48"
                />
                <SingleSelect
                  value={newRole}
                  onValueChange={setNewRole}
                  options={[
                    { value: "user", label: "User" },
                    { value: "admin", label: "Admin" },
                    { value: "agent", label: "Agent" },
                  ]}
                />
                <Button type="submit" size="sm">Create</Button>
              </form>
            </CardContent>
          </Card>
        )}

        <div className="space-y-2">
          {users.map((user) => (
            <Card key={user.id} className={!user.is_active ? "opacity-50" : ""}>
              <CardContent className="flex items-center justify-between py-3">
                <div className="flex items-center gap-3">
                  <span className="font-medium">{user.username}</span>
                  {user.email && (
                    <span className="text-sm text-muted-foreground">{user.email}</span>
                  )}
                  <Badge variant={roleColor(user.role)}>{user.role}</Badge>
                  {!user.is_active && (
                    <Badge variant="outline">inactive</Badge>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <SingleSelect
                    value={user.role}
                    onValueChange={(v) => changeRole(user, v)}
                    options={[
                      { value: "user", label: "User" },
                      { value: "admin", label: "Admin" },
                      { value: "agent", label: "Agent" },
                    ]}
                  />
                  {user.id !== currentUser?.id && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => toggleActive(user)}
                    >
                      {user.is_active ? "Deactivate" : "Activate"}
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </PageLayout>
  );
}
