"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { ModelInfo, DigestInfo } from "@/lib/api";
import { Activity, Cpu, BrainCircuit, Workflow } from "lucide-react";

const healthColor: Record<string, string> = {
  healthy: "text-green-500",
  degraded: "text-yellow-500",
  unhealthy: "text-red-500",
  unknown: "text-muted-foreground",
  idle: "text-muted-foreground",
  backoff: "text-red-500",
};

const healthBadgeVariant: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  healthy: "default",
  degraded: "secondary",
  unhealthy: "destructive",
  unknown: "outline",
  idle: "outline",
  backoff: "destructive",
};

function formatBackend(backend: string): string {
  if (backend === "bedrock") return "AWS Bedrock";
  if (backend === "local") return "Local";
  if (backend === "openai") return "OpenAI";
  if (backend === "ollama") return "Ollama";
  if (backend === "gemini") return "Gemini";
  return backend.charAt(0).toUpperCase() + backend.slice(1);
}

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return n.toString();
}

function timeAgo(iso: string | null): string {
  if (!iso) return "never";
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 60_000) return "just now";
  if (ms < 3_600_000) return `${Math.floor(ms / 60_000)}m ago`;
  if (ms < 86_400_000) return `${Math.floor(ms / 3_600_000)}h ago`;
  return `${Math.floor(ms / 86_400_000)}d ago`;
}

function ModelRow({
  label,
  model,
  icon: Icon,
}: {
  label: string;
  model: ModelInfo;
  icon: React.ComponentType<{ className?: string }>;
}) {
  return (
    <div className="flex items-center gap-3 py-2">
      <div className="rounded-md bg-muted p-1.5">
        <Icon className="h-3.5 w-3.5 text-muted-foreground" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">{label}</span>
          <Badge variant={healthBadgeVariant[model.health] ?? "outline"} className="text-[10px] px-1.5 py-0">
            <Activity className={`h-2.5 w-2.5 mr-0.5 ${healthColor[model.health] ?? ""}`} />
            {model.health}
          </Badge>
        </div>
        <p className="text-[11px] text-muted-foreground truncate">
          {formatBackend(model.backend)} &middot; <span className="font-mono">{model.model}</span>
        </p>
      </div>
      <div className="flex items-center gap-4 text-xs tabular-nums text-right shrink-0">
        <div>
          <p className="font-medium">{formatNumber(model.stats.calls)}</p>
          <p className="text-[10px] text-muted-foreground">calls</p>
        </div>
        <div>
          <p className="font-medium">{formatNumber(model.stats.tokens_est)}</p>
          <p className="text-[10px] text-muted-foreground">tokens</p>
        </div>
        <div>
          <p className={`font-medium ${model.stats.errors > 0 ? "text-red-500" : ""}`}>
            {model.stats.errors}
          </p>
          <p className="text-[10px] text-muted-foreground">errors</p>
        </div>
        <div className="w-14">
          <p className="font-medium">{timeAgo(model.stats.last_call)}</p>
          <p className="text-[10px] text-muted-foreground">last call</p>
        </div>
      </div>
    </div>
  );
}

function DigestRow({ digest }: { digest: DigestInfo }) {
  return (
    <div className="flex items-center gap-3 py-2">
      <div className="rounded-md bg-muted p-1.5">
        <Workflow className="h-3.5 w-3.5 text-muted-foreground" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">Digest Pipeline</span>
          <Badge variant={healthBadgeVariant[digest.health] ?? "outline"} className="text-[10px] px-1.5 py-0">
            <Activity className={`h-2.5 w-2.5 mr-0.5 ${healthColor[digest.health] ?? ""}`} />
            {digest.health}
          </Badge>
        </div>
        <p className="text-[11px] text-muted-foreground">
          State: {digest.state}
          {digest.queue_depth > 0 && ` \u00b7 ${digest.queue_depth} queued`}
        </p>
      </div>
      <div className="flex items-center gap-4 text-xs tabular-nums text-right shrink-0">
        <div>
          <p className="font-medium">{formatNumber(digest.batches_processed)}</p>
          <p className="text-[10px] text-muted-foreground">batches</p>
        </div>
        <div>
          <p className="font-medium">{formatNumber(digest.events_digested)}</p>
          <p className="text-[10px] text-muted-foreground">events</p>
        </div>
        <div>
          <p className="font-medium">
            {digest.avg_latency_s != null ? `${digest.avg_latency_s.toFixed(1)}s` : "\u2014"}
          </p>
          <p className="text-[10px] text-muted-foreground">avg lat</p>
        </div>
        <div className="w-14">
          <p className="font-medium">{timeAgo(digest.last_batch_time)}</p>
          <p className="text-[10px] text-muted-foreground">last batch</p>
        </div>
      </div>
    </div>
  );
}

export function HealthStrip({
  embedding,
  llm,
  digest,
}: {
  embedding?: ModelInfo;
  llm?: ModelInfo;
  digest?: DigestInfo;
}) {
  if (!embedding && !llm && !digest) return null;

  return (
    <Card>
      <CardContent className="p-4 space-y-0 divide-y divide-border">
        {embedding && <ModelRow label="Embedding" model={embedding} icon={Cpu} />}
        {llm && <ModelRow label="LLM" model={llm} icon={BrainCircuit} />}
        {digest && <DigestRow digest={digest} />}
      </CardContent>
    </Card>
  );
}
