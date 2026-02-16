"use client";

import Link from "next/link";
import { api, type Project } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useFetch } from "@/lib/use-fetch";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorState } from "@/components/error-state";
import { SkeletonList } from "@/components/skeleton-list";
import { PageLayout } from "@/components/page-layout";
import { FolderOpen } from "lucide-react";

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
                <CardHeader className="p-4 pb-2">
                  <CardTitle className="text-sm font-medium">
                    {p.name}
                  </CardTitle>
                </CardHeader>
                <CardContent className="p-4 pt-0">
                  <div className="flex items-baseline gap-1">
                    <span className="text-2xl font-semibold tabular-nums">
                      {p.memory_count}
                    </span>
                    <span className="text-sm text-muted-foreground">
                      memories
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {formatDate(p.created_at)}
                  </p>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </PageLayout>
  );
}
