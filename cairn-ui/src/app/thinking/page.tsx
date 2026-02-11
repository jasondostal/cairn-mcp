"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type ThinkingSequence } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useProjectSelector } from "@/lib/use-project-selector";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ErrorState } from "@/components/error-state";
import { MultiSelect } from "@/components/ui/multi-select";
import { PaginatedList } from "@/components/paginated-list";
import { SkeletonList } from "@/components/skeleton-list";
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

function SequencesList({ sequences, showProject }: { sequences: ThinkingSequence[]; showProject?: boolean }) {
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
  const { projects, loading: projectsLoading, error: projectsError } = useProjectSelector();
  const [sequences, setSequences] = useState<ThinkingSequence[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [projectFilter, setProjectFilter] = useState<string[]>([]);

  const showAll = projectFilter.length === 0;

  useEffect(() => {
    setLoading(true);
    setError(null);
    api
      .thinking(projectFilter.length ? projectFilter.join(",") : undefined)
      .then((r) => setSequences(r.items))
      .catch((err) => setError(err?.message || "Failed to load thinking sequences"))
      .finally(() => setLoading(false));
  }, [projectFilter]);

  const projectOptions = projects.map((p) => ({ value: p.name, label: p.name }));

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Thinking</h1>

      <MultiSelect
        options={projectOptions}
        value={projectFilter}
        onValueChange={setProjectFilter}
        placeholder="All projects"
        searchPlaceholder="Search projects…"
        maxCount={2}
      />

      {(loading || projectsLoading) && <SkeletonList count={4} />}

      {(error || projectsError) && <ErrorState message="Failed to load thinking sequences" detail={error || projectsError || undefined} />}

      {!loading && !projectsLoading && !error && !projectsError && sequences.length === 0 && (
        <p className="text-sm text-muted-foreground">
          {showAll
            ? "No thinking sequences yet."
            : `No thinking sequences for ${projectFilter.join(", ")}.`}
        </p>
      )}

      {!loading && !projectsLoading && !error && !projectsError && sequences.length > 0 && (
        <SequencesList sequences={sequences} showProject={showAll} />
      )}
    </div>
  );
}
