"use client";

import { useEffect, useState } from "react";
import { api, type TimelineMemory } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/error-state";
import { MemorySheet } from "@/components/memory-sheet";
import { Star, Tag } from "lucide-react";

function groupByDate(items: TimelineMemory[]): Map<string, TimelineMemory[]> {
  const groups = new Map<string, TimelineMemory[]>();
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);

  for (const item of items) {
    const date = new Date(item.created_at);
    date.setHours(0, 0, 0, 0);

    let label: string;
    if (date.getTime() === today.getTime()) {
      label = "Today";
    } else if (date.getTime() === yesterday.getTime()) {
      label = "Yesterday";
    } else {
      label = date.toLocaleDateString(undefined, {
        weekday: "long",
        month: "short",
        day: "numeric",
      });
    }

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
            <Badge variant="outline" className="font-mono text-xs">
              {memory.memory_type}
            </Badge>
            <span className="text-xs text-muted-foreground">
              {memory.project}
            </span>
          </div>
          <div className="flex items-center gap-0.5 shrink-0">
            <Star className="h-3 w-3 text-muted-foreground" />
            <span className="font-mono text-xs text-muted-foreground">
              {memory.importance.toFixed(2)}
            </span>
          </div>
        </div>

        {memory.summary && (
          <p className="text-sm font-medium">{memory.summary}</p>
        )}

        <p className="text-sm text-muted-foreground whitespace-pre-wrap leading-relaxed">
          {content}
        </p>

        {memory.tags.length > 0 && (
          <div className="flex items-center gap-1.5 flex-wrap">
            <Tag className="h-3 w-3 text-muted-foreground" />
            {memory.tags.map((t) => (
              <Badge key={t} variant="secondary" className="text-xs">
                {t}
              </Badge>
            ))}
          </div>
        )}

        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span>#{memory.id}</span>
          <span>&middot;</span>
          <span>
            {new Date(memory.created_at).toLocaleTimeString(undefined, {
              hour: "2-digit",
              minute: "2-digit",
            })}
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
  const [sheetId, setSheetId] = useState<number | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);

  function openSheet(id: number) {
    setSheetId(id);
    setSheetOpen(true);
  }

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

      {loading && (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      )}

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
