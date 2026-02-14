"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Cairn } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { usePageFilters } from "@/lib/use-page-filters";
import { PageFilters, DenseToggle } from "@/components/page-filters";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ErrorState } from "@/components/error-state";
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

function CairnDenseRow({ cairn, showProject }: { cairn: Cairn; showProject?: boolean }) {
  const truncated = cairn.narrative
    ? cairn.narrative.length > 100 ? cairn.narrative.slice(0, 100) + "…" : cairn.narrative
    : "";
  return (
    <Link
      href={`/cairns/${cairn.id}`}
      className="flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-accent/50 transition-colors"
    >
      <Landmark className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
      <span className="font-medium truncate shrink-0 max-w-[200px]">{cairn.title}</span>
      {truncated && <span className="flex-1 truncate text-muted-foreground">{truncated}</span>}
      {!truncated && <span className="flex-1" />}
      {cairn.is_compressed && (
        <Badge variant="secondary" className="text-xs shrink-0">
          <Archive className="mr-1 h-3 w-3" />
          compressed
        </Badge>
      )}
      {showProject && cairn.project && (
        <Badge variant="secondary" className="text-xs shrink-0">{cairn.project}</Badge>
      )}
      <Badge variant="outline" className="text-xs shrink-0">{cairn.session_name}</Badge>
      <span className="text-xs text-muted-foreground shrink-0 flex items-center gap-1">
        <Layers className="h-3 w-3" />
        {cairn.memory_count}
      </span>
      <span className="text-xs text-muted-foreground shrink-0">{formatDate(cairn.set_at)}</span>
    </Link>
  );
}

export default function CairnsPage() {
  const filters = usePageFilters({ defaultDense: false });
  const [cairns, setCairns] = useState<Cairn[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);    setError(null);    api
      .cairns(filters.showAllProjects ? undefined : filters.projectFilter.join(","))
      .then((data) => { if (!cancelled) setCairns(data); })
      .catch((err) => { if (!cancelled) setError(err?.message || "Failed to load cairns"); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [filters.projectFilter, filters.showAllProjects]);

  return (
    <PageLayout
      title="Cairns"
      titleExtra={<DenseToggle dense={filters.dense} onToggle={() => filters.setDense((d) => !d)} />}
      filters={<PageFilters filters={filters} />}
    >
      {(loading || filters.projectsLoading) && <SkeletonList count={4} height="h-24" />}

      {error && <ErrorState message="Failed to load cairns" detail={error} />}

      {!loading && !filters.projectsLoading && !error && cairns.length === 0 && (
        <EmptyState
          message={filters.showAllProjects ? "No cairns yet." : `No cairns for ${filters.projectFilter.join(", ")}.`}
          detail="Cairns are set at the end of sessions."
        />
      )}

      {!loading && !filters.projectsLoading && !error && cairns.length > 0 && (
        filters.dense ? (
          <div className="rounded-md border border-border divide-y divide-border">
            {cairns.map((c) => (
              <CairnDenseRow key={c.id} cairn={c} showProject={filters.showAllProjects} />
            ))}
          </div>
        ) : (
          <div className="space-y-2">
            {cairns.map((c) => (
              <CairnCard key={c.id} cairn={c} showProject={filters.showAllProjects} />
            ))}
          </div>
        )
      )}
    </PageLayout>
  );
}
