"use client";

import { useEffect, useState } from "react";
import { api, type ClusterResult } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { ErrorState } from "@/components/error-state";
import { Network } from "lucide-react";

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
                <Badge variant="outline" className="text-xs mr-1">
                  {m.memory_type}
                </Badge>
                {m.summary}
              </div>
            ))}
          </div>
        )}

        <p className="text-xs text-muted-foreground">
          {new Date(cluster.created_at).toLocaleDateString()}
        </p>
      </CardContent>
    </Card>
  );
}

export default function ClustersPage() {
  const [data, setData] = useState<ClusterResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [project, setProject] = useState("");
  const [topic, setTopic] = useState("");

  function load() {
    setLoading(true);
    setError(null);
    api
      .clusters({
        project: project || undefined,
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

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Clusters</h1>

      <div className="flex gap-2">
        <Input
          placeholder="Filter by project"
          value={project}
          onChange={(e) => setProject(e.target.value)}
          className="w-48"
        />
        <Input
          placeholder="Filter by topic"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          className="w-48"
        />
        <button
          onClick={load}
          className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          Apply
        </button>
      </div>

      {loading && (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
      )}

      {error && <ErrorState message="Failed to load clusters" detail={error} />}

      {!loading && !error && data && (
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
