"use client";

import { useState } from "react";
import { api, type Memory } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useMemorySheet } from "@/lib/use-memory-sheet";
import { useKeyboardNav } from "@/lib/use-keyboard-nav";
import { usePageFilters } from "@/lib/use-page-filters";
import { PageFilters, DenseToggle } from "@/components/page-filters";
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
import { EmptyState } from "@/components/empty-state";
import { PageLayout } from "@/components/page-layout";
import { Search, FileText } from "lucide-react";

const MEMORY_TYPES = [
  "note", "decision", "rule", "code-snippet", "learning",
  "research", "discussion", "progress", "task", "debug", "design",
] as const;

const TYPE_OPTIONS = MEMORY_TYPES.map((t) => ({ value: t, label: t }));

function ScoreBreakdown({ score, components }: { score: number; components?: { vector: number; keyword: number; tag: number } }) {
  const [showBreakdown, setShowBreakdown] = useState(false);
  const pct = (v: number) => score > 0 ? ((v / score) * 100).toFixed(0) : "0";

  return (
    <div
      className="relative"
      onMouseEnter={() => setShowBreakdown(true)}
      onMouseLeave={() => setShowBreakdown(false)}
    >
      <span className="font-mono text-xs text-muted-foreground cursor-help">
        {(score * 100).toFixed(0)}%
      </span>
      {showBreakdown && components && (
        <div className="absolute right-0 top-full z-50 mt-1 rounded-md border border-border bg-popover px-3 py-2 shadow-md whitespace-nowrap">
          <p className="text-xs font-medium mb-1.5">Score breakdown</p>
          <div className="space-y-1">
            {[
              { label: "Vector", value: components.vector, color: "bg-blue-500" },
              { label: "Keyword", value: components.keyword, color: "bg-amber-500" },
              { label: "Tag", value: components.tag, color: "bg-emerald-500" },
            ].map((s) => (
              <div key={s.label} className="flex items-center gap-2 text-xs">
                <div className={`h-2 w-2 rounded-full ${s.color}`} />
                <span className="text-muted-foreground w-14">{s.label}</span>
                <div className="w-16 h-1.5 bg-muted rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full ${s.color}`}
                    style={{ width: `${pct(s.value)}%` }}
                  />
                </div>
                <span className="font-mono text-muted-foreground w-8 text-right">
                  {pct(s.value)}%
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function MemoryCard({ memory, onSelect, isActive }: { memory: Memory; onSelect?: (id: number) => void; isActive?: boolean }) {
  const content =
    memory.content.length > 300
      ? memory.content.slice(0, 300) + "\u2026"
      : memory.content;

  return (
    <Card
      className={`transition-colors hover:border-primary/30 cursor-pointer ${isActive ? "border-primary/50 bg-accent/30" : ""}`}
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
              <ScoreBreakdown score={memory.score} components={memory.score_components} />
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

        {memory.related_files?.length > 0 && (
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

function MemoryDenseRow({ memory, onSelect, isActive }: { memory: Memory; onSelect?: (id: number) => void; isActive?: boolean }) {
  const truncated = memory.summary || (memory.content.length > 120 ? memory.content.slice(0, 120) + "\u2026" : memory.content);

  return (
    <div
      className={`flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-accent/50 transition-colors cursor-pointer ${isActive ? "bg-accent/30" : ""}`}
      onClick={() => onSelect?.(memory.id)}
    >
      <span className="font-mono text-xs text-muted-foreground shrink-0">#{memory.id}</span>
      <MemoryTypeBadge type={memory.memory_type} />
      <span className="flex-1 truncate">{truncated}</span>
      <span className="text-xs text-muted-foreground shrink-0">{memory.project}</span>
      {memory.score !== undefined && (
        <span className="font-mono text-xs text-muted-foreground shrink-0">
          {(memory.score * 100).toFixed(0)}%
        </span>
      )}
      <span className="shrink-0"><ImportanceBadge importance={memory.importance} /></span>
      <span className="text-xs text-muted-foreground shrink-0">{formatDate(memory.created_at)}</span>
    </div>
  );
}

function ResultsList({ results, dense, onSelect }: { results: Memory[]; dense: boolean; onSelect: (id: number) => void }) {
  const { activeIndex } = useKeyboardNav({
    itemCount: results.length,
    onSelect: (i) => onSelect(results[i].id),
  });

  if (dense) {
    return (
      <div className="rounded-md border border-border divide-y divide-border">
        {results.map((m, i) => (
          <MemoryDenseRow
            key={m.id}
            memory={m}
            onSelect={onSelect}
            isActive={i === activeIndex}
          />
        ))}
      </div>
    );
  }

  return (
    <PaginatedList
      items={results}
      noun="results"
      keyExtractor={(m) => m.id}
      renderItem={(m, i) => (
        <MemoryCard
          memory={m}
          onSelect={onSelect}
          isActive={i === activeIndex}
        />
      )}
    />
  );
}

export default function SearchPage() {
  const filters = usePageFilters({ defaultDense: false });
  const [query, setQuery] = useState("");
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
        project: filters.projectFilter.length ? filters.projectFilter.join(",") : undefined,
        type: filters.typeFilter.length ? filters.typeFilter.join(",") : undefined,
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
    <PageLayout
      title="Search"
      titleExtra={<DenseToggle dense={filters.dense} onToggle={() => filters.setDense((d) => !d)} />}
      filters={
        <form onSubmit={handleSearch} className="flex flex-col gap-3 w-full">
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
              {loading ? "Searching\u2026" : "Search"}
            </Button>
          </div>
          <PageFilters
            filters={filters}
            typeOptions={TYPE_OPTIONS}
            typePlaceholder="All types"
            extra={
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">Mode</span>
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
            }
          />
        </form>
      }
    >
      {loading && <SkeletonList count={5} height="h-32" />}

      {error && <ErrorState message="Search failed" detail={error} />}

      {!loading && !error && searched && results.length === 0 && (
        <EmptyState message="No results found." />
      )}

      {!loading && !error && results.length > 0 && (
        <ResultsList results={results} dense={filters.dense} onSelect={openSheet} />
      )}

      <MemorySheet
        memoryId={sheetId}
        open={sheetOpen}
        onOpenChange={setSheetOpen}
      />
    </PageLayout>
  );
}
