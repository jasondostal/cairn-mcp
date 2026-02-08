"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type ClusterResult } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useProjectSelector } from "@/lib/use-project-selector";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ErrorState } from "@/components/error-state";
import { MemoryTypeBadge } from "@/components/memory-type-badge";
import { ProjectSelector } from "@/components/project-selector";
import { SkeletonList } from "@/components/skeleton-list";
import { Network, Eye } from "lucide-react";

type Cluster = ClusterResult["clusters"][number];

function ClusterCard({ cluster }: { cluster: Cluster }) {
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
              <div key={m.id} className="text-sm">
                <span className="font-mono text-xs text-muted-foreground">
                  #{m.id}
                </span>{" "}
                <MemoryTypeBadge type={m.memory_type} />{" "}
                {m.summary}
              </div>
            ))}
          </div>
        )}

        <p className="text-xs text-muted-foreground">
          {formatDate(cluster.created_at)}
        </p>
      </CardContent>
    </Card>
  );
}

export default function ClustersPage() {
  const [data, setData] = useState<ClusterResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [topic, setTopic] = useState("");
  const [project, setProject] = useState("");
  const {
    projects,
    loading: projectsLoading,
  } = useProjectSelector();

  function load(proj?: string) {
    const p = proj ?? project;
    setLoading(true);
    setError(null);
    api
      .clusters({
        project: p || undefined,
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

  function handleProjectSelect(name: string) {
    // Toggle: clicking the same project deselects (shows all)
    const next = name === project ? "" : name;
    setProject(next);
    load(next);
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Clusters</h1>
        <Button asChild variant="outline" size="sm">
          <Link href="/clusters/visualization">
            <Eye className="mr-1.5 h-4 w-4" />
            Visualization
          </Link>
        </Button>
      </div>

      {/* Project selector buttons */}
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant={project === "" ? "default" : "outline"}
            size="sm"
            onClick={() => {
              if (project !== "") {
                setProject("");
                load("");
              }
            }}
          >
            All
          </Button>
          <ProjectSelector
            projects={projects}
            selected={project}
            onSelect={handleProjectSelect}
          />
        </div>
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
          <div className="space-y-3">
            {data.clusters.map((c) => (
              <ClusterCard key={c.id} cluster={c} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
