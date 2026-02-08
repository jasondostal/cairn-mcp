"use client";

import { useState } from "react";
import { api, type Memory } from "@/lib/api";
import { formatDate } from "@/lib/format";
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
import { PaginatedList } from "@/components/paginated-list";
import { Search, FileText } from "lucide-react";

function MemoryCard({ memory, onSelect }: { memory: Memory; onSelect?: (id: number) => void }) {
  const content =
    memory.content.length > 300
      ? memory.content.slice(0, 300) + "…"
      : memory.content;

  return (
    <Card
      className="transition-colors hover:border-primary/30 cursor-pointer"
      onClick={() => onSelect?.(memory.id)}
    >
      <CardContent className="space-y-3 p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2">
            <MemoryTypeBadge type={memory.memory_type} />
            <span className="text-xs text-muted-foreground">
              {memory.project}
            </span>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {memory.score !== undefined && (
              <span className="font-mono text-xs text-muted-foreground">
                {(memory.score * 100).toFixed(0)}%
              </span>
            )}
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

        {memory.related_files.length > 0 && (
          <div className="flex items-center gap-1.5 flex-wrap">
            <FileText className="h-3 w-3 text-muted-foreground" />
            {memory.related_files.map((f) => (
              <span
                key={f}
                className="font-mono text-xs text-muted-foreground"
              >
                {f}
              </span>
            ))}
          </div>
        )}

        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span>#{memory.id}</span>
          <span>&middot;</span>
          <span>{formatDate(memory.created_at)}</span>
          {memory.cluster && (
            <>
              <span>&middot;</span>
              <span>cluster: {memory.cluster.label}</span>
            </>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function ResultsList({ results, onSelect }: { results: Memory[]; onSelect: (id: number) => void }) {
  return (
    <PaginatedList
      items={results}
      noun="results"
      keyExtractor={(m) => m.id}
      renderItem={(m) => <MemoryCard memory={m} onSelect={onSelect} />}
    />
  );
}

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [project, setProject] = useState("");
  const [type, setType] = useState("");
  const [mode, setMode] = useState("semantic");
  const [results, setResults] = useState<Memory[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { sheetId, sheetOpen, setSheetOpen, openSheet } = useMemorySheet();

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setSearched(true);
    setError(null);
    try {
      const data = await api.search(query, {
        project: project || undefined,
        type: type || undefined,
        mode,
        limit: "100",
      });
      setResults(data.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
      setResults([]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Search</h1>

      <form onSubmit={handleSearch} className="space-y-3">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Search memories..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="pl-9"
            />
          </div>
          <Button type="submit" disabled={loading || !query.trim()}>
            {loading ? "Searching…" : "Search"}
          </Button>
        </div>

        <div className="flex gap-2 flex-wrap">
          <Input
            placeholder="Project filter"
            value={project}
            onChange={(e) => setProject(e.target.value)}
            className="w-40"
          />
          <Input
            placeholder="Type filter"
            value={type}
            onChange={(e) => setType(e.target.value)}
            className="w-40"
          />
          <div className="flex gap-1">
            {["semantic", "keyword", "vector"].map((m) => (
              <Button
                key={m}
                type="button"
                variant={mode === m ? "default" : "outline"}
                size="sm"
                onClick={() => setMode(m)}
              >
                {m}
              </Button>
            ))}
          </div>
        </div>
      </form>

      {loading && <SkeletonList count={5} height="h-32" />}

      {error && <ErrorState message="Search failed" detail={error} />}

      {!loading && !error && searched && results.length === 0 && (
        <p className="text-sm text-muted-foreground">No results found.</p>
      )}

      {!loading && !error && results.length > 0 && (
        <ResultsList results={results} onSelect={openSheet} />
      )}

      <MemorySheet
        memoryId={sheetId}
        open={sheetOpen}
        onOpenChange={setSheetOpen}
      />
    </div>
  );
}
