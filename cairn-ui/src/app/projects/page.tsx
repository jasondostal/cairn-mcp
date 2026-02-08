"use client";

import Link from "next/link";
import { api, type Project } from "@/lib/api";
import { useFetch } from "@/lib/use-fetch";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/error-state";

export default function ProjectsPage() {
  const { data: projects, loading, error } = useFetch<Project[]>(
    () => api.projects().then((r) => r.items),
    []
  );

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Projects</h1>
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Projects</h1>
        <ErrorState message="Failed to load projects" detail={error} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Projects</h1>
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
                  {new Date(p.created_at).toLocaleDateString()}
                </p>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
