"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type ThinkingSequence } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useProjectSelector } from "@/lib/use-project-selector";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ErrorState } from "@/components/error-state";
import { ProjectSelector } from "@/components/project-selector";
import { PaginatedList } from "@/components/paginated-list";
import { SkeletonList } from "@/components/skeleton-list";
import { Brain } from "lucide-react";

function SequenceCard({ sequence }: { sequence: ThinkingSequence }) {
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

function SequencesList({ sequences }: { sequences: ThinkingSequence[] }) {
  return (
    <PaginatedList
      items={sequences}
      noun="sequences"
      keyExtractor={(s) => s.sequence_id}
      renderItem={(s) => <SequenceCard sequence={s} />}
    />
  );
}

export default function ThinkingPage() {
  const { projects, selected, setSelected, loading: projectsLoading, error: projectsError } = useProjectSelector();
  const [sequences, setSequences] = useState<ThinkingSequence[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!selected) return;
    setLoading(true);
    setError(null);
    api
      .thinking(selected)
      .then((r) => setSequences(r.items))
      .catch((err) => setError(err?.message || "Failed to load thinking sequences"))
      .finally(() => setLoading(false));
  }, [selected]);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Thinking</h1>

      <ProjectSelector
        projects={projects}
        selected={selected}
        onSelect={setSelected}
      />

      {(loading || projectsLoading) && <SkeletonList count={4} />}

      {(error || projectsError) && <ErrorState message="Failed to load thinking sequences" detail={error || projectsError || undefined} />}

      {!loading && !projectsLoading && !error && !projectsError && sequences.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No thinking sequences for {selected}.
        </p>
      )}

      {!loading && !projectsLoading && !error && !projectsError && sequences.length > 0 && (
        <SequencesList sequences={sequences} />
      )}
    </div>
  );
}
