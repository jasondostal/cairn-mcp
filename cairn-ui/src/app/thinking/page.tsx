"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type ThinkingSequence } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { usePageFilters } from "@/lib/use-page-filters";
import { PageFilters, DenseToggle } from "@/components/page-filters";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ErrorState } from "@/components/error-state";
import { PaginatedList } from "@/components/paginated-list";
import { SkeletonList } from "@/components/skeleton-list";
import { EmptyState } from "@/components/empty-state";
import { PageLayout } from "@/components/page-layout";
import { Brain } from "lucide-react";

function SequenceCard({ sequence, showProject }: { sequence: ThinkingSequence; showProject?: boolean }) {
  return (
    <Link href={`/thinking/${sequence.sequence_id}`}>
      <Card className="transition-colors hover:border-primary/30">
        <CardHeader className="p-4 pb-2">
          <div className="flex items-center gap-2">
            <Brain className="h-4 w-4 text-muted-foreground" />
            <CardTitle className="text-sm font-medium">
              {sequence.goal}
            </CardTitle>
          </div>
        </CardHeader>
        <CardContent className="p-4 pt-0">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            {showProject && sequence.project && (
              <Badge variant="secondary" className="text-xs">
                {sequence.project}
              </Badge>
            )}
            <Badge
              variant={
                sequence.status === "completed" ? "secondary" : "default"
              }
              className="text-xs"
            >
              {sequence.status}
            </Badge>
            <span>
              {sequence.thought_count} thought
              {sequence.thought_count !== 1 && "s"}
            </span>
            <span>·</span>
            <span>
              {formatDate(sequence.created_at)}
            </span>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

function SequenceDenseRow({ sequence, showProject }: { sequence: ThinkingSequence; showProject?: boolean }) {
  return (
    <Link href={`/thinking/${sequence.sequence_id}`}>
      <div className="flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-accent/50 transition-colors cursor-pointer">
        <Brain className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <span className="flex-1 truncate">{sequence.goal}</span>
        {showProject && sequence.project && (
          <Badge variant="secondary" className="text-xs shrink-0">{sequence.project}</Badge>
        )}
        <Badge
          variant={sequence.status === "completed" ? "secondary" : "default"}
          className="text-xs shrink-0"
        >
          {sequence.status}
        </Badge>
        <span className="text-xs text-muted-foreground shrink-0">
          {sequence.thought_count} thought{sequence.thought_count !== 1 && "s"}
        </span>
        <span className="text-xs text-muted-foreground shrink-0">{formatDate(sequence.created_at)}</span>
      </div>
    </Link>
  );
}

function SequencesList({ sequences, showProject, dense }: { sequences: ThinkingSequence[]; showProject?: boolean; dense?: boolean }) {
  if (dense) {
    return (
      <div className="rounded-md border border-border divide-y divide-border">
        {sequences.map((s) => (
          <SequenceDenseRow key={s.sequence_id} sequence={s} showProject={showProject} />
        ))}
      </div>
    );
  }
  return (
    <PaginatedList
      items={sequences}
      noun="sequences"
      keyExtractor={(s) => s.sequence_id}
      renderItem={(s) => <SequenceCard sequence={s} showProject={showProject} />}
    />
  );
}

export default function ThinkingPage() {
  const filters = usePageFilters();
  const [sequences, setSequences] = useState<ThinkingSequence[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    api
      .thinking(filters.showAllProjects ? undefined : filters.projectFilter.join(","))
      .then((r) => setSequences(r.items))
      .catch((err) => setError(err?.message || "Failed to load thinking sequences"))
      .finally(() => setLoading(false));
  }, [filters.projectFilter, filters.showAllProjects]);

  return (
    <PageLayout
      title="Thinking"
      titleExtra={<DenseToggle dense={filters.dense} onToggle={() => filters.setDense((d) => !d)} />}
      filters={<PageFilters filters={filters} />}
    >
      {(loading || filters.projectsLoading) && <SkeletonList count={4} />}

      {error && <ErrorState message="Failed to load thinking sequences" detail={error} />}

      {!loading && !filters.projectsLoading && !error && sequences.length === 0 && (
        <EmptyState
          message={filters.showAllProjects
            ? "No thinking sequences yet."
            : `No thinking sequences for ${filters.projectFilter.join(", ")}.`}
          detail="Thinking sequences are created via the MCP think tool for structured reasoning."
        />
      )}

      {!loading && !filters.projectsLoading && !error && sequences.length > 0 && (
        <SequencesList sequences={sequences} showProject={filters.showAllProjects} dense={filters.dense} />
      )}
    </PageLayout>
  );
}
