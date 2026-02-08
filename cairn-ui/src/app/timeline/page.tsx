"use client";

import { useEffect, useState } from "react";
import { api, type TimelineMemory } from "@/lib/api";
import { formatRelativeDate, formatTime } from "@/lib/format";
import { useMemorySheet } from "@/lib/use-memory-sheet";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/error-state";
import { MemorySheet } from "@/components/memory-sheet";
import { MemoryTypeBadge } from "@/components/memory-type-badge";
import { ImportanceBadge } from "@/components/importance-badge";
import { TagList } from "@/components/tag-list";
import { SkeletonList } from "@/components/skeleton-list";

function groupByDate(items: TimelineMemory[]): Map<string, TimelineMemory[]> {
  const groups = new Map<string, TimelineMemory[]>();

  for (const item of items) {
    const label = formatRelativeDate(item.created_at);
    const group = groups.get(label) ?? [];
    group.push(item);
    groups.set(label, group);
  }

  return groups;
}

function TimelineCard({
  memory,
  onSelect,
}: {
  memory: TimelineMemory;
  onSelect?: (id: number) => void;
}) {
  const content =
    memory.content.length > 200
      ? memory.content.slice(0, 200) + "\u2026"
      : memory.content;

  return (
    <Card
      className="transition-colors hover:border-primary/30 cursor-pointer"
      onClick={() => onSelect?.(memory.id)}
    >
      <CardContent className="space-y-2 p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2">
            <MemoryTypeBadge type={memory.memory_type} />
            <span className="text-xs text-muted-foreground">
              {memory.project}
            </span>
          </div>
          <div className="shrink-0">
            <ImportanceBadge importance={memory.importance} />
          </div>
        </div>

        {memory.summary && (
          <p className="text-sm font-medium">{memory.summary}</p>
        )}

        <p className="text-sm text-muted-foreground whitespace-pre-wrap leading-relaxed">
          {content}
        </p>

        <TagList tags={memory.tags} />

        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span>#{memory.id}</span>
          <span>&middot;</span>
          <span>
            {formatTime(memory.created_at)}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

export default function TimelinePage() {
  const [items, setItems] = useState<TimelineMemory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [project, setProject] = useState("");
  const [type, setType] = useState("");
  const [days, setDays] = useState("7");
  const { sheetId, sheetOpen, setSheetOpen, openSheet } = useMemorySheet();

  function load() {
    setLoading(true);
    setError(null);
    api
      .timeline({
        project: project || undefined,
        type: type || undefined,
        days: days || "7",
        limit: "100",
      })
      .then((data) => setItems(data.items))
      .catch((err) => setError(err?.message || "Failed to load timeline"))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const groups = groupByDate(items);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Timeline</h1>

      <div className="flex gap-2 flex-wrap">
        <Input
          placeholder="Filter by project"
          value={project}
          onChange={(e) => setProject(e.target.value)}
          className="w-40"
        />
        <Input
          placeholder="Filter by type"
          value={type}
          onChange={(e) => setType(e.target.value)}
          className="w-40"
        />
        <Input
          placeholder="Days"
          type="number"
          value={days}
          onChange={(e) => setDays(e.target.value)}
          className="w-20"
        />
        <Button onClick={load}>Apply</Button>
      </div>

      {loading && <SkeletonList count={5} />}

      {error && <ErrorState message="Failed to load timeline" detail={error} />}

      {!loading && !error && items.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No memories in the last {days} days.
        </p>
      )}

      {!loading && !error && items.length > 0 && (
        <div className="space-y-6">
          {Array.from(groups.entries()).map(([label, memories]) => (
            <div key={label}>
              <h2 className="mb-3 text-sm font-medium text-muted-foreground sticky top-0 bg-background py-1">
                {label}
                <span className="ml-2 text-xs">({memories.length})</span>
              </h2>
              <div className="space-y-2 border-l-2 border-border pl-4">
                {memories.map((m) => (
                  <TimelineCard key={m.id} memory={m} onSelect={openSheet} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      <MemorySheet
        memoryId={sheetId}
        open={sheetOpen}
        onOpenChange={setSheetOpen}
      />
    </div>
  );
}
