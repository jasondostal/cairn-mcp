"use client";

import { useEffect, useState } from "react";
import { api, type Status, type Settings } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ErrorState } from "@/components/error-state";
import { SkeletonList } from "@/components/skeleton-list";
import { PageLayout } from "@/components/page-layout";
import {
  Cpu,
  Database,
  Brain,
  Shield,
  BarChart3,
  Terminal,
  Layers,
  Zap,
  CheckCircle2,
  XCircle,
} from "lucide-react";

function StatusBadge({ enabled }: { enabled: boolean }) {
  return enabled ? (
    <Badge variant="default" className="gap-1 text-xs">
      <CheckCircle2 className="h-3 w-3" />
      enabled
    </Badge>
  ) : (
    <Badge variant="secondary" className="gap-1 text-xs">
      <XCircle className="h-3 w-3" />
      disabled
    </Badge>
  );
}

function InfoRow({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-center justify-between py-1.5 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-mono text-xs">{value}</span>
    </div>
  );
}

const CAPABILITY_LABELS: Record<string, string> = {
  query_expansion: "Query Expansion",
  relationship_extract: "Relationship Extraction",
  rule_conflict_check: "Rule Conflict Check",
  session_synthesis: "Session Synthesis",
  consolidation: "Memory Consolidation",
  confidence_gating: "Confidence Gating",
  event_digest: "Event Digest",
  reranking: "Cross-Encoder Reranking",
  type_routing: "Type Routing",
  spreading_activation: "Spreading Activation",
  mca_gate: "MCA Gate",
  knowledge_extraction: "Knowledge Extraction",
  search_v2: "Search V2 (Intent-Routed)",
};

export default function SettingsPage() {
  const [status, setStatus] = useState<Status | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    Promise.all([api.status(), api.settings()])
      .then(([s, cfg]) => {
        setStatus(s);
        setSettings(cfg);
      })
      .catch((err) => setError(err?.message || "Failed to load settings"))
      .finally(() => setLoading(false));
  }, []);

  return (
    <PageLayout title="Settings">
      {loading && <SkeletonList count={4} height="h-32" />}
      {error && <ErrorState message="Failed to load settings" detail={error} />}

      {!loading && !error && status && settings && (
        <div className="grid gap-4 md:grid-cols-2">
          {/* System Overview */}
          <Card>
            <CardHeader className="p-4 pb-2">
              <CardTitle className="flex items-center gap-2 text-sm">
                <Database className="h-4 w-4" />
                System Overview
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4 pt-0 divide-y divide-border">
              <InfoRow label="Version" value={`v${status.version}`} />
              <InfoRow label="Status" value={status.status} />
              <InfoRow label="Memories" value={status.memories.toLocaleString()} />
              <InfoRow label="Projects" value={status.projects} />
              <InfoRow label="Clusters" value={status.clusters} />
              <InfoRow label="Transport" value={settings.transport} />
              <InfoRow label="HTTP Port" value={settings.http_port} />
            </CardContent>
          </Card>

          {/* Embedding */}
          <Card>
            <CardHeader className="p-4 pb-2">
              <CardTitle className="flex items-center gap-2 text-sm">
                <Layers className="h-4 w-4" />
                Embedding
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4 pt-0 divide-y divide-border">
              <InfoRow label="Backend" value={settings.embedding.backend} />
              <InfoRow label="Model" value={settings.embedding.model} />
              <InfoRow label="Dimensions" value={settings.embedding.dimensions} />
              {status.models.embedding && (
                <>
                  <InfoRow label="Calls" value={status.models.embedding.stats.calls.toLocaleString()} />
                  <InfoRow label="Health" value={status.models.embedding.health} />
                </>
              )}
            </CardContent>
          </Card>

          {/* LLM */}
          <Card>
            <CardHeader className="p-4 pb-2">
              <CardTitle className="flex items-center gap-2 text-sm">
                <Brain className="h-4 w-4" />
                LLM
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4 pt-0 divide-y divide-border">
              <InfoRow label="Backend" value={settings.llm.backend} />
              <InfoRow label="Model" value={settings.llm.model} />
              <div className="flex items-center justify-between py-1.5 text-sm">
                <span className="text-muted-foreground">Enrichment</span>
                <StatusBadge enabled={settings.enrichment_enabled} />
              </div>
              {status.models.llm && (
                <>
                  <InfoRow label="Calls" value={status.models.llm.stats.calls.toLocaleString()} />
                  <InfoRow label="Health" value={status.models.llm.health} />
                </>
              )}
            </CardContent>
          </Card>

          {/* Reranker */}
          <Card>
            <CardHeader className="p-4 pb-2">
              <CardTitle className="flex items-center gap-2 text-sm">
                <Zap className="h-4 w-4" />
                Reranker
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4 pt-0 divide-y divide-border">
              <InfoRow label="Backend" value={settings.reranker.backend} />
              <InfoRow label="Model" value={settings.reranker.model} />
              <InfoRow label="Candidates" value={settings.reranker.candidates} />
            </CardContent>
          </Card>

          {/* Security & Infra */}
          <Card>
            <CardHeader className="p-4 pb-2">
              <CardTitle className="flex items-center gap-2 text-sm">
                <Shield className="h-4 w-4" />
                Security & Infrastructure
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4 pt-0 divide-y divide-border">
              <div className="flex items-center justify-between py-1.5 text-sm">
                <span className="text-muted-foreground">Authentication</span>
                <StatusBadge enabled={settings.auth.enabled} />
              </div>
              <div className="flex items-center justify-between py-1.5 text-sm">
                <span className="text-muted-foreground">Terminal</span>
                <Badge variant="secondary" className="text-xs font-mono">
                  {settings.terminal.backend}
                </Badge>
              </div>
            </CardContent>
          </Card>

          {/* Analytics */}
          <Card>
            <CardHeader className="p-4 pb-2">
              <CardTitle className="flex items-center gap-2 text-sm">
                <BarChart3 className="h-4 w-4" />
                Analytics
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4 pt-0 divide-y divide-border">
              <div className="flex items-center justify-between py-1.5 text-sm">
                <span className="text-muted-foreground">Enabled</span>
                <StatusBadge enabled={settings.analytics.enabled} />
              </div>
              <InfoRow label="Retention" value={`${settings.analytics.retention_days} days`} />
            </CardContent>
          </Card>

          {/* LLM Capabilities — full width */}
          <Card className="md:col-span-2">
            <CardHeader className="p-4 pb-2">
              <CardTitle className="flex items-center gap-2 text-sm">
                <Cpu className="h-4 w-4" />
                LLM Capabilities
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4 pt-0">
              <div className="grid gap-x-8 gap-y-1 sm:grid-cols-2 lg:grid-cols-3">
                {Object.entries(settings.capabilities).map(([key, enabled]) => (
                  <div
                    key={key}
                    className="flex items-center justify-between py-1.5 text-sm"
                  >
                    <span className={enabled ? "" : "text-muted-foreground"}>
                      {CAPABILITY_LABELS[key] || key}
                    </span>
                    <StatusBadge enabled={enabled} />
                  </div>
                ))}
              </div>
              <p className="mt-4 text-xs text-muted-foreground">
                Capabilities are configured via environment variables (CAIRN_LLM_*). Restart the server to apply changes.
              </p>
            </CardContent>
          </Card>

          {/* Memory Types */}
          <Card className="md:col-span-2">
            <CardHeader className="p-4 pb-2">
              <CardTitle className="flex items-center gap-2 text-sm">
                <Terminal className="h-4 w-4" />
                Memory Types
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4 pt-0">
              <div className="flex flex-wrap gap-2">
                {Object.entries(status.types)
                  .sort(([, a], [, b]) => b - a)
                  .map(([type, count]) => (
                    <Badge key={type} variant="outline" className="gap-1.5 font-mono text-xs">
                      {type}
                      <span className="text-muted-foreground">{count}</span>
                    </Badge>
                  ))}
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </PageLayout>
  );
}
