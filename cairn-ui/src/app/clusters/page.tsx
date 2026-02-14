"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type ClusterResult } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useMemorySheet } from "@/lib/use-memory-sheet";
import { usePageFilters } from "@/lib/use-page-filters";
import { PageFilters, DenseToggle } from "@/components/page-filters";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ErrorState } from "@/components/error-state";
import { MemoryTypeBadge } from "@/components/memory-type-badge";
import { MemorySheet } from "@/components/memory-sheet";
import { SkeletonList } from "@/components/skeleton-list";
import { PageLayout } from "@/components/page-layout";
import { Network, Eye, ArrowRight } from "lucide-react";

type Cluster = ClusterResult["clusters"][number];

function ClusterCard({ cluster, onMemorySelect }: { cluster: Cluster; onMemorySelect: (id: number) => void }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <Card>
      <CardHeader className="p-4 pb-2">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2">
            <Network className="h-4 w-4 text-muted-foreground" />
            <CardTitle className="text-sm font-medium">
              {cluster.label}
            </CardTitle>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="secondary" className="font-mono text-xs">
              {cluster.member_count} memories
            </Badge>
            <Badge
              variant="outline"
              className="font-mono text-xs"
            >
              {(cluster.confidence * 100).toFixed(0)}%
            </Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 p-4 pt-0">
        <p className="text-sm text-muted-foreground">{cluster.summary}</p>

        <button
          onClick={() => setExpanded(!expanded)}
          className="text-xs text-primary hover:underline"
        >
          {expanded ? "Hide" : "Show"} sample memories (
          {cluster.sample_memories.length})
        </button>

        {expanded && (
          <div className="space-y-2 border-l-2 border-border pl-3">
            {cluster.sample_memories.map((m) => (
              <div
                key={m.id}
                className="text-sm cursor-pointer hover:bg-accent/50 rounded-md px-2 py-1 -mx-2 transition-colors"
                onClick={() => onMemorySelect(m.id)}
              >
                <span className="font-mono text-xs text-muted-foreground">
                  #{m.id}
                </span>{" "}
                <MemoryTypeBadge type={m.memory_type} />{" "}
                {m.summary}
              </div>
            ))}
            {cluster.member_count > cluster.sample_memories.length && (
              <Link
                href={`/search?query=${encodeURIComponent(cluster.label)}`}
                className="flex items-center gap-1 text-xs text-primary hover:underline px-2"
              >
                View all {cluster.member_count} members
                <ArrowRight className="h-3 w-3" />
              </Link>
            )}
          </div>
        )}

        <p className="text-xs text-muted-foreground">
          {formatDate(cluster.created_at)}
        </p>
      </CardContent>
    </Card>
  );
}

function ClusterDenseRow({ cluster, onMemorySelect }: { cluster: Cluster; onMemorySelect: (id: number) => void }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div>
      <div
        className="flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-accent/50 transition-colors cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <Network className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <span className="flex-1 truncate">{cluster.label}</span>
        <Badge variant="secondary" className="font-mono text-xs shrink-0">
          {cluster.member_count}
        </Badge>
        <Badge variant="outline" className="font-mono text-xs shrink-0">
          {(cluster.confidence * 100).toFixed(0)}%
        </Badge>
        <span className="text-xs text-muted-foreground shrink-0">{formatDate(cluster.created_at)}</span>
      </div>
      {expanded && (
        <div className="space-y-1 border-l-2 border-border ml-6 pl-3 py-2">
          <p className="text-xs text-muted-foreground mb-2">{cluster.summary}</p>
          {cluster.sample_memories.map((m) => (
            <div
              key={m.id}
              className="text-sm cursor-pointer hover:bg-accent/50 rounded-md px-2 py-0.5 transition-colors"
              onClick={() => onMemorySelect(m.id)}
            >
              <span className="font-mono text-xs text-muted-foreground">#{m.id}</span>{" "}
              <MemoryTypeBadge type={m.memory_type} />{" "}
              <span className="text-xs">{m.summary}</span>
            </div>
          ))}
          {cluster.member_count > cluster.sample_memories.length && (
            <Link
              href={`/search?query=${encodeURIComponent(cluster.label)}`}
              className="flex items-center gap-1 text-xs text-primary hover:underline px-2 pt-1"
            >
              View all {cluster.member_count} members
              <ArrowRight className="h-3 w-3" />
            </Link>
          )}
        </div>
      )}
    </div>
  );
}

export default function ClustersPage() {
  const filters = usePageFilters({ defaultDense: false });
  const [data, setData] = useState<ClusterResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [topic, setTopic] = useState("");
  const { sheetId, sheetOpen, setSheetOpen, openSheet } = useMemorySheet();

  function load(proj?: string[]) {
    const p = proj ?? filters.projectFilter;
    setLoading(true);
    setError(null);
    api
      .clusters({
        project: p.length ? p.join(",") : undefined,
        topic: topic || undefined,
      })
      .then(setData)
      .catch((err) => setError(err?.message || "Failed to load clusters"))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleProjectChange(value: string[]) {
    filters.setProjectFilter(value);
    load(value);
  }

  return (
    <PageLayout
      title="Clusters"
      titleExtra={<>
        <DenseToggle dense={filters.dense} onToggle={() => filters.setDense((d) => !d)} />
        <Button asChild variant="outline" size="sm">
          <Link href="/clusters/visualization">
            <Eye className="mr-1.5 h-4 w-4" />
            Visualization
          </Link>
        </Button>
      </>}
      filters={
        <div className="space-y-2">
          <PageFilters
            filters={{
              ...filters,
              setProjectFilter: handleProjectChange,
            }}
          />
          <div className="flex gap-2">
            <Input
              placeholder="Filter by topic"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              className="w-48"
            />
            <Button onClick={() => load()} size="sm">Apply</Button>
          </div>
        </div>
      }
    >
      {loading && <SkeletonList count={4} height="h-32" />}

      {error && <ErrorState message="Failed to load clusters" detail={error} />}

      {!loading && !error && data && data.cluster_count === 0 && (
        <div className="flex h-[200px] items-center justify-center rounded-lg border border-border bg-card">
          <div className="text-center">
            <p className="text-sm text-muted-foreground">
              No clusters found.
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              Clustering needs 10+ memories in a project. Try selecting a
              specific project or storing more memories.
            </p>
          </div>
        </div>
      )}

      {!loading && !error && data && data.cluster_count > 0 && (
        <>
          <p className="text-sm text-muted-foreground">
            {data.cluster_count} cluster{data.cluster_count !== 1 && "s"}
          </p>
          {filters.dense ? (
            <div className="rounded-md border border-border divide-y divide-border">
              {data.clusters.map((c) => (
                <ClusterDenseRow key={c.id} cluster={c} onMemorySelect={openSheet} />
              ))}
            </div>
          ) : (
            <div className="space-y-3">
              {data.clusters.map((c) => (
                <ClusterCard key={c.id} cluster={c} onMemorySelect={openSheet} />
              ))}
            </div>
          )}
        </>
      )}

      <MemorySheet
        memoryId={sheetId}
        open={sheetOpen}
        onOpenChange={setSheetOpen}
      />
    </PageLayout>
  );
}
