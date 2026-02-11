"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Cairn } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useProjectSelector } from "@/lib/use-project-selector";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ErrorState } from "@/components/error-state";
import { MultiSelect } from "@/components/ui/multi-select";
import { SkeletonList } from "@/components/skeleton-list";
import { EmptyState } from "@/components/empty-state";
import { PageLayout } from "@/components/page-layout";
import { Landmark, Archive, Layers } from "lucide-react";

function CairnCard({ cairn, showProject }: { cairn: Cairn; showProject?: boolean }) {
  return (
    <Link href={`/cairns/${cairn.id}`}>
      <Card className="transition-colors hover:bg-accent/50">
        <CardContent className="p-4 space-y-2">
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-2">
              <Landmark className="h-4 w-4 shrink-0 text-muted-foreground" />
              <h3 className="text-sm font-medium">{cairn.title}</h3>
            </div>
            <div className="flex items-center gap-1.5 shrink-0">
              {cairn.is_compressed && (
                <Badge variant="secondary" className="text-xs">
                  <Archive className="mr-1 h-3 w-3" />
                  compressed
                </Badge>
              )}
              <Badge variant="outline" className="text-xs">
                {cairn.session_name}
              </Badge>
            </div>
          </div>

          {cairn.narrative && (
            <p className="text-sm text-muted-foreground line-clamp-2">
              {cairn.narrative}
            </p>
          )}

          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            {showProject && cairn.project && (
              <Badge variant="secondary" className="text-xs">
                {cairn.project}
              </Badge>
            )}
            <span className="flex items-center gap-1">
              <Layers className="h-3 w-3" />
              {cairn.memory_count} {cairn.memory_count === 1 ? "stone" : "stones"}
            </span>
            <span>{formatDate(cairn.set_at)}</span>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

export default function CairnsPage() {
  const { projects, loading: projectsLoading, error: projectsError } = useProjectSelector();
  const [cairns, setCairns] = useState<Cairn[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [projectFilter, setProjectFilter] = useState<string[]>([]);

  const showAll = projectFilter.length === 0;

  useEffect(() => {
    setLoading(true);
    setError(null);
    api
      .cairns(projectFilter.length ? projectFilter.join(",") : undefined)
      .then(setCairns)
      .catch((err) => setError(err?.message || "Failed to load cairns"))
      .finally(() => setLoading(false));
  }, [projectFilter]);

  const projectOptions = projects.map((p) => ({ value: p.name, label: p.name }));

  return (
    <PageLayout
      title="Cairns"
      filters={
        <MultiSelect
          options={projectOptions}
          value={projectFilter}
          onValueChange={setProjectFilter}
          placeholder="All projects"
          searchPlaceholder="Search projects…"
          maxCount={2}
        />
      }
    >
      {(loading || projectsLoading) && <SkeletonList count={4} height="h-24" />}

      {(error || projectsError) && <ErrorState message="Failed to load cairns" detail={error || projectsError || undefined} />}

      {!loading && !projectsLoading && !error && !projectsError && cairns.length === 0 && (
        <EmptyState
          message={showAll ? "No cairns yet." : `No cairns for ${projectFilter.join(", ")}.`}
          detail="Cairns are set at the end of sessions."
        />
      )}

      {!loading && !projectsLoading && !error && !projectsError && cairns.length > 0 && (
        <div className="space-y-2">
          {cairns.map((c) => (
            <CairnCard key={c.id} cairn={c} showProject={showAll} />
          ))}
        </div>
      )}
    </PageLayout>
  );
}
