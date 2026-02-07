"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Status, type Project } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Database,
  FolderOpen,
  Network,
  Cpu,
  BrainCircuit,
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
  const [status, setStatus] = useState<Status | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.status(), api.projects()])
      .then(([s, p]) => {
        setStatus(s);
        setProjects(p);
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <div className="grid grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
        <div className="grid grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      </div>
    );
  }

  if (!status) return null;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Dashboard</h1>

      {/* Stat cards */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Memories" value={status.memories} icon={Database} />
        <StatCard label="Projects" value={status.projects} icon={FolderOpen} />
        <StatCard label="Clusters" value={status.clusters} icon={Network} />
        <StatCard
          label="Embedding"
          value={status.embedding_model.replace("all-", "")}
          icon={Cpu}
        />
      </div>

      {/* LLM info */}
      <Card>
        <CardContent className="flex items-center gap-4 p-4">
          <div className="rounded-md bg-muted p-2">
            <BrainCircuit className="h-5 w-5 text-muted-foreground" />
          </div>
          <div className="flex flex-1 items-center justify-between">
            <div>
              <p className="text-sm font-medium">
                {status.llm_backend === "bedrock" ? "AWS Bedrock" : "Ollama"}
              </p>
              <p className="font-mono text-xs text-muted-foreground">
                {status.llm_model}
              </p>
            </div>
            <Badge
              variant={status.status === "healthy" ? "default" : "destructive"}
            >
              {status.status}
            </Badge>
          </div>
        </CardContent>
      </Card>

      {/* Memory types */}
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

      {/* Project cards */}
      <div>
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">
          Projects
        </h2>
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-4">
          {projects.map((p) => (
            <ProjectCard key={p.id} project={p} />
          ))}
        </div>
      </div>
    </div>
  );
}
