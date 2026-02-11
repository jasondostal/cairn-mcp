"use client";

import Link from "next/link";
import { api, type Status, type ModelInfo, type DigestInfo, type Project } from "@/lib/api";
import { useFetch } from "@/lib/use-fetch";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ErrorState } from "@/components/error-state";
import { SkeletonList } from "@/components/skeleton-list";
import {
  Activity,
  Database,
  FolderOpen,
  Network,
  Cpu,
  BrainCircuit,
  Workflow,
} from "lucide-react";

function StatCard({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string | number;
  icon: React.ComponentType<{ className?: string }>;
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-4 p-4">
        <div className="rounded-md bg-muted p-2">
          <Icon className="h-5 w-5 text-muted-foreground" />
        </div>
        <div>
          <p className="text-sm text-muted-foreground">{label}</p>
          <p className="text-2xl font-semibold tabular-nums">{value}</p>
        </div>
      </CardContent>
    </Card>
  );
}

function TypeBadge({ type, count }: { type: string; count: number }) {
  return (
    <Badge variant="secondary" className="gap-1 font-mono text-xs">
      {type}
      <span className="text-muted-foreground">{count}</span>
    </Badge>
  );
}

const healthColor: Record<string, string> = {
  healthy: "text-green-500",
  degraded: "text-yellow-500",
  unhealthy: "text-red-500",
  unknown: "text-muted-foreground",
};

const healthBadgeVariant: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  healthy: "default",
  degraded: "secondary",
  unhealthy: "destructive",
  unknown: "outline",
};

function formatBackend(backend: string): string {
  if (backend === "bedrock") return "AWS Bedrock";
  if (backend === "local") return "Local";
  if (backend === "openai") return "OpenAI";
  return backend.charAt(0).toUpperCase() + backend.slice(1);
}

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return n.toString();
}

function ModelCard({
  label,
  model,
  icon: Icon,
}: {
  label: string;
  model: ModelInfo | undefined;
  icon: React.ComponentType<{ className?: string }>;
}) {
  if (!model) return null;
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <div className="rounded-md bg-muted p-2">
              <Icon className="h-4 w-4 text-muted-foreground" />
            </div>
            <span className="text-sm font-medium">{label}</span>
          </div>
          <Badge variant={healthBadgeVariant[model.health] ?? "outline"}>
            <Activity className={`h-3 w-3 mr-1 ${healthColor[model.health] ?? ""}`} />
            {model.health}
          </Badge>
        </div>
        <div className="mb-2">
          <p className="text-xs text-muted-foreground">{formatBackend(model.backend)}</p>
          <p className="font-mono text-xs truncate" title={model.model}>{model.model}</p>
        </div>
        <div className="grid grid-cols-3 gap-2 text-center">
          <div>
            <p className="text-lg font-semibold tabular-nums">{formatNumber(model.stats.calls)}</p>
            <p className="text-[10px] text-muted-foreground">calls</p>
          </div>
          <div>
            <p className="text-lg font-semibold tabular-nums">{formatNumber(model.stats.tokens_est)}</p>
            <p className="text-[10px] text-muted-foreground">tokens</p>
          </div>
          <div>
            <p className={`text-lg font-semibold tabular-nums ${model.stats.errors > 0 ? "text-red-500" : ""}`}>
              {model.stats.errors}
            </p>
            <p className="text-[10px] text-muted-foreground">errors</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

const digestHealthColor: Record<string, string> = {
  healthy: "text-green-500",
  degraded: "text-yellow-500",
  backoff: "text-red-500",
  idle: "text-muted-foreground",
};

const digestHealthBadge: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  healthy: "default",
  degraded: "secondary",
  backoff: "destructive",
  idle: "outline",
};

function DigestCard({ digest }: { digest: DigestInfo | undefined }) {
  if (!digest) return null;
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <div className="rounded-md bg-muted p-2">
              <Workflow className="h-4 w-4 text-muted-foreground" />
            </div>
            <span className="text-sm font-medium">Digest Pipeline</span>
          </div>
          <Badge variant={digestHealthBadge[digest.health] ?? "outline"}>
            <Activity className={`h-3 w-3 mr-1 ${digestHealthColor[digest.health] ?? ""}`} />
            {digest.health}
          </Badge>
        </div>
        <div className="mb-2">
          <p className="text-xs text-muted-foreground">State: {digest.state}</p>
          {digest.queue_depth > 0 && (
            <p className="font-mono text-xs">
              {digest.queue_depth} batch{digest.queue_depth !== 1 ? "es" : ""} queued
            </p>
          )}
        </div>
        <div className="grid grid-cols-3 gap-2 text-center">
          <div>
            <p className="text-lg font-semibold tabular-nums">{formatNumber(digest.batches_processed)}</p>
            <p className="text-[10px] text-muted-foreground">batches</p>
          </div>
          <div>
            <p className="text-lg font-semibold tabular-nums">{formatNumber(digest.events_digested)}</p>
            <p className="text-[10px] text-muted-foreground">events</p>
          </div>
          <div>
            <p className="text-lg font-semibold tabular-nums">
              {digest.avg_latency_s != null ? `${digest.avg_latency_s.toFixed(1)}s` : "—"}
            </p>
            <p className="text-[10px] text-muted-foreground">avg latency</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function ProjectCard({ project }: { project: Project }) {
  return (
    <Link href={`/projects/${encodeURIComponent(project.name)}`}>
      <Card className="transition-colors hover:border-primary/30">
        <CardHeader className="p-4 pb-2">
          <CardTitle className="text-sm font-medium">{project.name}</CardTitle>
        </CardHeader>
        <CardContent className="p-4 pt-0">
          <div className="flex items-baseline gap-1">
            <span className="text-2xl font-semibold tabular-nums">
              {project.memory_count}
            </span>
            <span className="text-sm text-muted-foreground">memories</span>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

export default function Dashboard() {
  const {
    data: status,
    loading: statusLoading,
    error: statusError,
  } = useFetch<Status>(() => api.status());
  const {
    data: projects,
    loading: projectsLoading,
    error: projectsError,
  } = useFetch<Project[]>(() => api.projects().then((r) => r.items));

  const loading = statusLoading || projectsLoading;
  const error = statusError || projectsError;

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <SkeletonList count={4} height="h-20" gap="grid grid-cols-2 gap-4 lg:grid-cols-4" />
        <SkeletonList count={6} height="h-24" gap="grid grid-cols-2 gap-4 lg:grid-cols-3" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <ErrorState
          message="Failed to load dashboard"
          detail={error}
        />
      </div>
    );
  }

  if (!status) return null;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Dashboard</h1>

      <div className="grid grid-cols-3 gap-4">
        <StatCard label="Memories" value={status.memories} icon={Database} />
        <StatCard label="Projects" value={status.projects} icon={FolderOpen} />
        <StatCard label="Clusters" value={status.clusters} icon={Network} />
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        <ModelCard label="Embedding" model={status.models?.embedding} icon={Cpu} />
        <ModelCard label="LLM" model={status.models?.llm} icon={BrainCircuit} />
        <DigestCard digest={status.digest} />
      </div>

      <div>
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">
          Memory Types
        </h2>
        <div className="flex flex-wrap gap-2">
          {Object.entries(status.types)
            .sort(([, a], [, b]) => b - a)
            .map(([type, count]) => (
              <TypeBadge key={type} type={type} count={count} />
            ))}
        </div>
      </div>

      <div>
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">
          Projects
        </h2>
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-4">
          {(projects || []).map((p) => (
            <ProjectCard key={p.id} project={p} />
          ))}
        </div>
      </div>
    </div>
  );
}
