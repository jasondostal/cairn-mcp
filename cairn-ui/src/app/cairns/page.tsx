"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Cairn } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useProjectSelector } from "@/lib/use-project-selector";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/error-state";
import { ProjectSelector } from "@/components/project-selector";
import { SkeletonList } from "@/components/skeleton-list";
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
  const { projects, selected, setSelected, loading: projectsLoading, error: projectsError } = useProjectSelector();
  const [cairns, setCairns] = useState<Cairn[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    if (!showAll && !selected) return;
    setLoading(true);
    setError(null);
    api
      .cairns(showAll ? undefined : selected)
      .then(setCairns)
      .catch((err) => setError(err?.message || "Failed to load cairns"))
      .finally(() => setLoading(false));
  }, [selected, showAll]);

  function handleShowAll() {
    setShowAll(true);
  }

  function handleSelectProject(name: string) {
    setShowAll(false);
    setSelected(name);
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Cairns</h1>

      <div className="flex gap-1 flex-wrap">
        <Button
          variant={showAll ? "default" : "outline"}
          size="sm"
          onClick={handleShowAll}
        >
          All
        </Button>
        <ProjectSelector
          projects={projects}
          selected={showAll ? "" : selected}
          onSelect={handleSelectProject}
        />
      </div>

      {(loading || projectsLoading) && <SkeletonList count={4} height="h-24" />}

      {(error || projectsError) && <ErrorState message="Failed to load cairns" detail={error || projectsError || undefined} />}

      {!loading && !projectsLoading && !error && !projectsError && cairns.length === 0 && (
        <p className="text-sm text-muted-foreground">
          {showAll
            ? "No cairns yet. Cairns are set at the end of sessions."
            : `No cairns for ${selected}. Cairns are set at the end of sessions.`}
        </p>
      )}

      {!loading && !projectsLoading && !error && !projectsError && cairns.length > 0 && (
        <div className="space-y-2">
          {cairns.map((c) => (
            <CairnCard key={c.id} cairn={c} showProject={showAll} />
          ))}
        </div>
      )}
    </div>
  );
}
