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
import { useAuth } from "@/components/auth-provider";
import { api, type Group, type GroupDetail } from "@/lib/api";
import { Plus, Users2, Shield, ChevronDown, ChevronRight, Trash2, UserPlus, FolderPlus } from "lucide-react";

function DisabledState() {
  return (
    <PageLayout title="Groups" icon={Users2}>
      <div className="flex flex-col items-center justify-center h-full text-center max-w-lg mx-auto gap-6 p-8">
        <div className="rounded-full bg-muted p-4">
          <Shield className="h-8 w-8 text-muted-foreground" />
        </div>
        <div>
          <h2 className="text-xl font-semibold mb-2">Authentication not enabled</h2>
          <p className="text-sm text-muted-foreground">
            Enable authentication to manage user groups.
          </p>
        </div>
      </div>
    </PageLayout>
  );
}

function GroupRow({
  group,
  onDelete,
  onRefresh,
}: {
  group: Group;
  onDelete: (id: number) => void;
  onRefresh: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [detail, setDetail] = useState<GroupDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [newMemberId, setNewMemberId] = useState("");
  const [newProjectName, setNewProjectName] = useState("");
  const [newProjectRole, setNewProjectRole] = useState("member");

  const loadDetail = useCallback(async () => {
    setLoadingDetail(true);
    try {
      const d = await api.group(group.id);
      setDetail(d);
    } catch {
      toast.error("Failed to load group details");
    } finally {
      setLoadingDetail(false);
    }
  }, [group.id]);

  const toggleExpand = () => {
    if (!expanded && !detail) loadDetail();
    setExpanded(!expanded);
  };

  const handleAddMember = async () => {
    const uid = parseInt(newMemberId, 10);
    if (!uid) return;
    try {
      await api.addGroupMember(group.id, uid);
      toast.success("Member added");
      setNewMemberId("");
      loadDetail();
      onRefresh();
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to add member");
    }
  };

  const handleRemoveMember = async (userId: number) => {
    try {
      await api.removeGroupMember(group.id, userId);
      toast.success("Member removed");
      loadDetail();
      onRefresh();
    } catch {
      toast.error("Failed to remove member");
    }
  };

  const handleAddProject = async () => {
    if (!newProjectName.trim()) return;
    try {
      await api.addGroupProject(group.id, newProjectName.trim(), newProjectRole);
      toast.success("Project assigned");
      setNewProjectName("");
      setNewProjectRole("member");
      loadDetail();
      onRefresh();
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to assign project");
    }
  };

  const handleRemoveProject = async (projectName: string) => {
    try {
      await api.removeGroupProject(group.id, projectName);
      toast.success("Project unassigned");
      loadDetail();
      onRefresh();
    } catch {
      toast.error("Failed to remove project");
    }
  };

  return (
    <div className="border rounded-lg">
      <div
        className="flex items-center justify-between p-3 cursor-pointer hover:bg-muted/50"
        onClick={toggleExpand}
      >
        <div className="flex items-center gap-3">
          {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          <span className="font-medium text-sm">{group.name}</span>
          <Badge variant={group.source === "oidc" ? "secondary" : "outline"} className="text-[10px]">
            {group.source}
          </Badge>
        </div>
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          <span>{group.member_count} members</span>
          <span>{group.project_count} projects</span>
          <Button
            variant="ghost"
            size="xs"
            onClick={(e) => { e.stopPropagation(); onDelete(group.id); }}
            className="text-destructive hover:text-destructive"
          >
            <Trash2 className="h-3 w-3" />
          </Button>
        </div>
      </div>

      {expanded && (
        <div className="border-t p-3 space-y-4 bg-muted/20">
          {loadingDetail ? (
            <p className="text-xs text-muted-foreground">Loading...</p>
          ) : detail ? (
            <>
              {group.description && (
                <p className="text-xs text-muted-foreground">{group.description}</p>
              )}

              {/* Members */}
              <div>
                <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">Members</h4>
                {detail.members.length === 0 ? (
                  <p className="text-xs text-muted-foreground">No members</p>
                ) : (
                  <div className="space-y-1">
                    {detail.members.map((m) => (
                      <div key={m.user_id} className="flex items-center justify-between text-xs">
                        <span>{m.username} <span className="text-muted-foreground">({m.role})</span></span>
                        <Button variant="ghost" size="xs" onClick={() => handleRemoveMember(m.user_id)}>
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
                <div className="flex items-center gap-2 mt-2">
                  <Input
                    placeholder="User ID"
                    value={newMemberId}
                    onChange={(e) => setNewMemberId(e.target.value)}
                    className="h-7 text-xs w-24"
                    onClick={(e) => e.stopPropagation()}
                  />
                  <Button size="xs" variant="outline" onClick={handleAddMember}>
                    <UserPlus className="h-3 w-3 mr-1" /> Add
                  </Button>
                </div>
              </div>

              {/* Projects */}
              <div>
                <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">Projects</h4>
                {detail.projects.length === 0 ? (
                  <p className="text-xs text-muted-foreground">No projects</p>
                ) : (
                  <div className="space-y-1">
                    {detail.projects.map((p) => (
                      <div key={p.project_id} className="flex items-center justify-between text-xs">
                        <span>{p.project_name} <Badge variant="outline" className="text-[10px] ml-1">{p.role}</Badge></span>
                        <Button variant="ghost" size="xs" onClick={() => handleRemoveProject(p.project_name)}>
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
                <div className="flex items-center gap-2 mt-2">
                  <Input
                    placeholder="Project name"
                    value={newProjectName}
                    onChange={(e) => setNewProjectName(e.target.value)}
                    className="h-7 text-xs w-36"
                    onClick={(e) => e.stopPropagation()}
                  />
                  <SingleSelect
                    options={[
                      { value: "member", label: "member" },
                      { value: "owner", label: "owner" },
                    ]}
                    value={newProjectRole}
                    onValueChange={setNewProjectRole}
                    className="h-7 text-xs"
                  />
                  <Button size="xs" variant="outline" onClick={handleAddProject}>
                    <FolderPlus className="h-3 w-3 mr-1" /> Add
                  </Button>
                </div>
              </div>
            </>
          ) : null}
        </div>
      )}
    </div>
  );
}

export default function AdminGroupsPage() {
  const router = useRouter();
  const { user: currentUser, authEnabled } = useAuth();
  const [groups, setGroups] = useState<Group[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");

  const fetchGroups = useCallback(async () => {
    try {
      const data = await api.groups();
      setGroups(data.items || []);
    } catch {
      toast.error("Failed to load groups");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!authEnabled) {
      setLoading(false);
      return;
    }
    if (!currentUser || currentUser.role !== "admin") {
      router.push("/");
      return;
    }
    fetchGroups();
  }, [authEnabled, currentUser, router, fetchGroups]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.createGroup({ name: newName, description: newDescription });
      toast.success(`Group "${newName}" created`);
      setShowCreate(false);
      setNewName("");
      setNewDescription("");
      fetchGroups();
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to create group");
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await api.deleteGroup(id);
      toast.success("Group deleted");
      fetchGroups();
    } catch {
      toast.error("Failed to delete group");
    }
  };

  if (loading) {
    return (
      <PageLayout title="Groups" icon={Users2}>
        <SkeletonList count={3} />
      </PageLayout>
    );
  }

  if (!authEnabled) {
    return <DisabledState />;
  }

  return (
    <PageLayout title="Groups" icon={Users2}>
      <div className="space-y-4">
        <div className="flex justify-end">
          <Button size="sm" onClick={() => setShowCreate(!showCreate)}>
            <Plus className="mr-1 h-4 w-4" /> Create Group
          </Button>
        </div>

        {showCreate && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Create Group</CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleCreate} className="flex flex-wrap gap-3 items-end">
                <Input
                  placeholder="Group name"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  required
                  className="w-48"
                />
                <Input
                  placeholder="Description (optional)"
                  value={newDescription}
                  onChange={(e) => setNewDescription(e.target.value)}
                  className="w-64"
                />
                <Button type="submit" size="sm">Create</Button>
              </form>
            </CardContent>
          </Card>
        )}

        {groups.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">
            <Users2 className="h-8 w-8 mx-auto mb-3 opacity-50" />
            <p className="text-sm">No groups yet. Create one to organize user access.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {groups.map((g) => (
              <GroupRow
                key={g.id}
                group={g}
                onDelete={handleDelete}
                onRefresh={fetchGroups}
              />
            ))}
          </div>
        )}
      </div>
    </PageLayout>
  );
}
