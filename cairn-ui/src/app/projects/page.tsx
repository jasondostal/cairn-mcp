"use client";

import Link from "next/link";
import { api, type Project } from "@/lib/api";
import { useFetch } from "@/lib/use-fetch";
import { Card, CardContent } from "@/components/ui/card";
import { ErrorState } from "@/components/error-state";
import { SkeletonList } from "@/components/skeleton-list";
import { PageLayout } from "@/components/page-layout";
import { Brain, FileText, CheckSquare, FolderOpen } from "lucide-react";

function relativeTime(dateStr: string | null): string {
  if (!dateStr) return "No activity";
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "Active just now";
  if (diffMin < 60) return `Active ${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `Active ${diffHr}h ago`;
  const diffDays = Math.floor(diffHr / 24);
  if (diffDays === 1) return "Active yesterday";
  if (diffDays < 30) return `Active ${diffDays}d ago`;
  return `Active ${date.toLocaleDateString([], { month: "short", day: "numeric" })}`;
}

export default function ProjectsPage() {
  const { data: projects, loading, error } = useFetch<Project[]>(
    () => api.projects().then((r) => r.items),
    []
  );

  return (
    <PageLayout title="Projects">
      {loading && (
        <SkeletonList count={8} gap="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-4" />
      )}

      {error && <ErrorState message="Failed to load projects" detail={error} />}

      {!loading && !error && (projects ?? []).length === 0 && (
        <div className="text-center py-12 text-muted-foreground">
          <FolderOpen className="mx-auto mb-3 h-10 w-10 opacity-30" />
          <p className="text-sm">No projects yet.</p>
          <p className="text-xs mt-1 opacity-60">
            Projects are created automatically when you store your first memory.
          </p>
        </div>
      )}

      {!loading && !error && (projects ?? []).length > 0 && (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-4">
          {(projects ?? []).map((p) => (
            <Link key={p.id} href={`/projects/${encodeURIComponent(p.name)}`}>
              <Card className="transition-colors hover:border-primary/30">
                <CardContent className="p-4 space-y-2">
                  <div className="font-semibold text-sm truncate">{p.name}</div>
                  <div className="flex items-center gap-3 text-xs text-muted-foreground">
                    <span className="flex items-center gap-1">
                      <Brain className="h-3 w-3" />
                      {p.memory_count}
                    </span>
                    <span className="flex items-center gap-1">
                      <FileText className="h-3 w-3" />
                      {p.doc_count}
                    </span>
                    <span className="flex items-center gap-1">
                      <CheckSquare className="h-3 w-3" />
                      {p.work_item_count}
                    </span>
                  </div>
                  <div className="text-[11px] text-muted-foreground/70">
                    {relativeTime(p.last_activity)}
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </PageLayout>
  );
}
