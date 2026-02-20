"use client";

import { useEffect, useState, useCallback } from "react";
import { api, type Status, type SettingsResponse } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SingleSelect } from "@/components/ui/single-select";
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip";
import { ErrorState } from "@/components/error-state";
import { SkeletonList } from "@/components/skeleton-list";
import { PageLayout } from "@/components/page-layout";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import {
  Cpu,
  Database,
  Brain,
  Shield,
  BarChart3,
  Terminal,
  Layers,
  Zap,
  Save,
  RotateCcw,
  AlertTriangle,
  Eye,
  EyeOff,
  CircleHelp,
  Route,
  Share2,
  Coins,
} from "lucide-react";

// --- Source badge ---

function SourceBadge({ source }: { source: "default" | "env" | "db" }) {
  const variants: Record<string, { variant: "default" | "secondary" | "outline"; label: string }> = {
    default: { variant: "outline", label: "default" },
    env: { variant: "secondary", label: "env" },
    db: { variant: "default", label: "db" },
  };
  const { variant, label } = variants[source] || variants.default;
  return <Badge variant={variant} className="text-[10px] px-1.5 py-0">{label}</Badge>;
}

// --- Capability metadata ---

interface CapabilityMeta { label: string; description: string; }

const CAPABILITY_META: Record<string, CapabilityMeta> = {
  relationship_extract: {
    label: "Relationship Extraction",
    description: "Extracts entity relationships from stored memories and builds a knowledge graph. Runs during enrichment on store.",
  },
  rule_conflict_check: {
    label: "Rule Conflict Check",
    description: "Detects contradictions between new rule-type memories and existing rules. Flags conflicts before storage.",
  },
  session_synthesis: {
    label: "Session Synthesis",
    description: "Generates narrative summaries from session event streams. Synthesizes tool calls and responses into coherent session stories.",
  },
  consolidation: {
    label: "Memory Consolidation",
    description: "Finds and merges semantically duplicate memories. Runs on-demand via the consolidate endpoint.",
  },
  confidence_gating: {
    label: "Confidence Gating",
    description: "Filters search results below a confidence threshold. Prevents low-quality matches from reaching the caller.",
  },
  reranking: {
    label: "Cross-Encoder Reranking",
    description: "Re-scores search candidates with a cross-encoder model for higher precision. Adds latency but significantly improves relevance.",
  },
  type_routing: {
    label: "Type Routing",
    description: "Routes search queries to memory-type-specific retrieval strategies based on detected intent.",
  },
  spreading_activation: {
    label: "Spreading Activation",
    description: "Traverses the knowledge graph from search hits to find contextually related memories. Expands results via graph edges.",
  },
  mca_gate: {
    label: "MCA Gate",
    description: "Multi-criteria assessment that scores memories on relevance, recency, and importance before returning results.",
  },
  knowledge_extraction: {
    label: "Knowledge Extraction",
    description: "Extracts entities, facts, and relationships from session digests and feeds them into the knowledge graph.",
  },
  search_v2: {
    label: "Search V2 (Intent-Routed)",
    description: "Intent-aware search pipeline that classifies queries and applies specialized retrieval strategies per intent type.",
  },
};

const SECRET_KEYS = new Set([
  "llm.gemini_api_key", "llm.openai_api_key",
  "auth.api_key", "terminal.encryption_key",
  "db.password", "embedding.openai_api_key",
  "workspace.password", "neo4j.password",
]);

// --- Tooltip descriptions for key non-capability settings ---

const SETTING_TOOLTIPS: Record<string, string> = {
  enrichment_enabled: "When enabled, memories are enriched with LLM-generated tags, summaries, and importance scores on store.",
  "reranker.candidates": "Initial candidates retrieved before cross-encoder re-scoring. Higher = better recall, slower.",
  ingest_chunk_size: "Token count per chunk when ingesting documents. Larger = more context, less granularity.",
  ingest_chunk_overlap: "Token overlap between adjacent chunks. Prevents information loss at boundaries.",
  "analytics.cost_embedding_per_1k": "Used for cost estimation in the analytics dashboard. Set to your provider's pricing.",
  "analytics.cost_llm_input_per_1k": "Used for cost estimation in the analytics dashboard. Set to your provider's pricing.",
  "analytics.cost_llm_output_per_1k": "Used for cost estimation in the analytics dashboard. Set to your provider's pricing.",
  "router.enabled": "Enable multi-model routing. Routes LLM calls to different backends/models based on task tier (capable, fast, chat).",
  "router.capable.backend": "LLM backend for capable-tier tasks. Empty = use default llm.backend.",
  "router.capable.model": "Model ID for capable tier. Empty = use default model for the backend.",
  "router.capable.daily_budget": "Max tokens/day for capable tier. 0 = unlimited.",
  "router.fast.backend": "LLM backend for fast-tier tasks. Empty = use default llm.backend.",
  "router.fast.model": "Model ID for fast tier. Empty = use default model for the backend.",
  "router.fast.daily_budget": "Max tokens/day for fast tier. 0 = unlimited.",
  "router.chat.backend": "LLM backend for chat-tier tasks. Empty = use default llm.backend.",
  "router.chat.model": "Model ID for chat tier. Empty = use default model for the backend.",
  "router.chat.daily_budget": "Max tokens/day for chat tier. 0 = unlimited.",
  "neo4j.uri": "Bolt URI for the Neo4j knowledge graph. Example: bolt://localhost:7687.",
  "neo4j.user": "Neo4j authentication username.",
  "neo4j.password": "Neo4j authentication password.",
  "neo4j.database": "Neo4j database name. Defaults to 'neo4j'.",
  "budget.rules": "Token budget for rules() responses. Controls maximum output length.",
  "budget.search": "Token budget for search() responses.",
  "budget.recall": "Token budget for recall() responses.",
  "budget.cairn_stack": "Token budget for cairns(action='stack') responses.",
  "budget.insights": "Token budget for insights() responses.",
  "budget.workspace": "Token budget for workspace build_context() responses.",
};

// --- Tooltip label helper ---

function TooltipLabel({ children, description }: { children: React.ReactNode; description?: string }) {
  if (!description) return <>{children}</>;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex items-center gap-1 cursor-help">
          {children}
          <CircleHelp className="h-3 w-3 text-muted-foreground/50" />
        </span>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-[280px]">
        <p>{description}</p>
      </TooltipContent>
    </Tooltip>
  );
}

// --- Toggle component ---

function Toggle({
  checked, onChange, disabled,
}: { checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors
        ${checked ? "bg-primary" : "bg-muted"}
        ${disabled ? "opacity-50 cursor-not-allowed" : ""}
      `}
    >
      <span className={`pointer-events-none block h-3.5 w-3.5 rounded-full bg-background shadow-lg transition-transform ${checked ? "translate-x-4" : "translate-x-0.5"}`} />
    </button>
  );
}

// --- Read-only row ---

function ReadOnlyRow({ label, value, source }: { label: string; value: string | number | boolean; source?: "default" | "env" | "db" }) {
  return (
    <div className="flex items-center justify-between py-1.5 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <div className="flex items-center gap-2">
        {source && <SourceBadge source={source} />}
        <span className="font-mono text-xs">{String(value)}</span>
      </div>
    </div>
  );
}

// --- Section card with save ---

interface SectionProps {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
  dirty: boolean;
  onSave: () => void;
  saving: boolean;
  className?: string;
}

function SectionCard({ icon, title, children, dirty, onSave, saving, className }: SectionProps) {
  return (
    <Card className={className}>
      <CardHeader className="p-4 pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-sm">
            {icon}
            {title}
          </CardTitle>
          {dirty && (
            <Button size="xs" onClick={onSave} disabled={saving}>
              <Save className="h-3 w-3" />
              {saving ? "Saving..." : "Save"}
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="p-4 pt-0 space-y-0 divide-y divide-border">
        {children}
      </CardContent>
    </Card>
  );
}

// --- Editable fields ---

function EditableText({
  label, settingKey, value, source, secret, localEdits, setLocalEdits, onReset, tooltip,
}: {
  label: string; settingKey: string; value: string; source: "default" | "env" | "db";
  secret?: boolean; localEdits: Record<string, string>; setLocalEdits: (e: Record<string, string>) => void;
  onReset: (key: string) => void; tooltip?: string;
}) {
  const [show, setShow] = useState(false);
  const editedValue = settingKey in localEdits ? localEdits[settingKey] : value;
  const isSecret = secret || SECRET_KEYS.has(settingKey);
  const dirty = settingKey in localEdits;

  return (
    <div className={cn("flex items-center justify-between gap-3 py-1.5 text-sm", dirty && "bg-primary/5 rounded-sm px-2 -mx-2")}>
      <div className="flex items-center gap-2 shrink-0">
        {dirty && <span className="size-1 rounded-full bg-primary" />}
        <TooltipLabel description={tooltip}>
          <span className="text-muted-foreground">{label}</span>
        </TooltipLabel>
        <SourceBadge source={source} />
        {source === "db" && (
          <button onClick={() => onReset(settingKey)} className="text-muted-foreground hover:text-foreground" title="Reset to default">
            <RotateCcw className="h-3 w-3" />
          </button>
        )}
      </div>
      <div className="flex items-center gap-1.5 min-w-0 max-w-[280px]">
        <Input
          type={isSecret && !show ? "password" : "text"}
          value={editedValue}
          onChange={(e) => setLocalEdits({ ...localEdits, [settingKey]: e.target.value })}
          className="h-7 text-xs font-mono"
        />
        {isSecret && (
          <button onClick={() => setShow(!show)} className="text-muted-foreground hover:text-foreground shrink-0">
            {show ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
          </button>
        )}
      </div>
    </div>
  );
}

function EditableNumber({
  label, settingKey, value, source, localEdits, setLocalEdits, onReset, min, tooltip,
}: {
  label: string; settingKey: string; value: number; source: "default" | "env" | "db";
  localEdits: Record<string, string>; setLocalEdits: (e: Record<string, string>) => void;
  onReset: (key: string) => void; min?: number; tooltip?: string;
}) {
  const editedValue = settingKey in localEdits ? localEdits[settingKey] : String(value);
  const dirty = settingKey in localEdits;

  return (
    <div className={cn("flex items-center justify-between gap-3 py-1.5 text-sm", dirty && "bg-primary/5 rounded-sm px-2 -mx-2")}>
      <div className="flex items-center gap-2 shrink-0">
        {dirty && <span className="size-1 rounded-full bg-primary" />}
        <TooltipLabel description={tooltip}>
          <span className="text-muted-foreground">{label}</span>
        </TooltipLabel>
        <SourceBadge source={source} />
        {source === "db" && (
          <button onClick={() => onReset(settingKey)} className="text-muted-foreground hover:text-foreground" title="Reset to default">
            <RotateCcw className="h-3 w-3" />
          </button>
        )}
      </div>
      <Input
        type="number"
        value={editedValue}
        min={min ?? 0}
        onChange={(e) => setLocalEdits({ ...localEdits, [settingKey]: e.target.value })}
        className="h-7 text-xs font-mono w-24"
      />
    </div>
  );
}

function EditableToggle({
  label, settingKey, value, source, localEdits, setLocalEdits, onReset, tooltip,
}: {
  label: string; settingKey: string; value: boolean; source: "default" | "env" | "db";
  localEdits: Record<string, string>; setLocalEdits: (e: Record<string, string>) => void;
  onReset: (key: string) => void; tooltip?: string;
}) {
  const editedValue = settingKey in localEdits
    ? localEdits[settingKey] === "true"
    : value;
  const dirty = settingKey in localEdits;

  return (
    <div className={cn("flex items-center justify-between py-1.5 text-sm", dirty && "bg-primary/5 rounded-sm px-2 -mx-2")}>
      <div className="flex items-center gap-2">
        {dirty && <span className="size-1 rounded-full bg-primary" />}
        <TooltipLabel description={tooltip}>
          <span className={editedValue ? "text-sm" : "text-muted-foreground text-sm"}>{label}</span>
        </TooltipLabel>
        <SourceBadge source={source} />
        {source === "db" && (
          <button onClick={() => onReset(settingKey)} className="text-muted-foreground hover:text-foreground" title="Reset to default">
            <RotateCcw className="h-3 w-3" />
          </button>
        )}
      </div>
      <Toggle
        checked={editedValue}
        onChange={(v) => setLocalEdits({ ...localEdits, [settingKey]: v ? "true" : "false" })}
      />
    </div>
  );
}

function EditableSelect({
  label, settingKey, value, source, options, localEdits, setLocalEdits, onReset, tooltip,
}: {
  label: string; settingKey: string; value: string; source: "default" | "env" | "db";
  options: string[]; localEdits: Record<string, string>; setLocalEdits: (e: Record<string, string>) => void;
  onReset: (key: string) => void; tooltip?: string;
}) {
  const editedValue = settingKey in localEdits ? localEdits[settingKey] : value;
  const dirty = settingKey in localEdits;

  return (
    <div className={cn("flex items-center justify-between gap-3 py-1.5 text-sm", dirty && "bg-primary/5 rounded-sm px-2 -mx-2")}>
      <div className="flex items-center gap-2 shrink-0">
        {dirty && <span className="size-1 rounded-full bg-primary" />}
        <TooltipLabel description={tooltip}>
          <span className="text-muted-foreground">{label}</span>
        </TooltipLabel>
        <SourceBadge source={source} />
        {source === "db" && (
          <button onClick={() => onReset(settingKey)} className="text-muted-foreground hover:text-foreground" title="Reset to default">
            <RotateCcw className="h-3 w-3" />
          </button>
        )}
      </div>
      <SingleSelect
        options={options.map((o) => ({ value: o, label: o }))}
        value={editedValue}
        onValueChange={(v) => setLocalEdits({ ...localEdits, [settingKey]: v })}
        className="h-7 text-xs font-mono"
      />
    </div>
  );
}

// --- Main page ---

export default function SettingsPage() {
  const [status, setStatus] = useState<Status | null>(null);
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [localEdits, setLocalEdits] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    Promise.all([api.status(), api.settingsV2()])
      .then(([s, cfg]) => {
        setStatus(s);
        setSettings(cfg);
        setLocalEdits({});
      })
      .catch((err) => setError(err?.message || "Failed to load settings"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const val = (key: string) => settings?.values[key];
  type SettingSource = "default" | "env" | "db";
  const src = (key: string): SettingSource =>
    (settings?.sources[key] as SettingSource) || "default";

  const isExperimental = (key: string) =>
    settings?.experimental?.includes(`capabilities.${key}`) ?? false;

  // Collect dirty keys for a section
  const dirtyKeys = (prefix: string) =>
    Object.keys(localEdits).filter((k) => k.startsWith(prefix));

  const sectionDirty = (prefix: string) => dirtyKeys(prefix).length > 0;

  const saveKeys = async (keys: string[], savingId: string) => {
    if (keys.length === 0) return;

    const updates: Record<string, string | number | boolean> = {};
    for (const k of keys) updates[k] = localEdits[k];

    setSaving(savingId);
    try {
      const result = await api.updateSettings(updates);
      setSettings(result);
      const remaining = { ...localEdits };
      for (const k of keys) delete remaining[k];
      setLocalEdits(remaining);
      toast.success("Settings saved. Restart to apply changes.");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(null);
    }
  };

  const saveSection = (prefix: string) => saveKeys(dirtyKeys(prefix), prefix);

  const handleReset = async (key: string) => {
    try {
      const result = await api.resetSetting(key);
      setSettings(result);
      const remaining = { ...localEdits };
      delete remaining[key];
      setLocalEdits(remaining);
      toast.success(`Reset ${key}. Restart to apply.`);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to reset");
    }
  };

  // Split capabilities into stable and experimental
  const allCapabilities = Object.entries(CAPABILITY_META);
  const stableCapabilities = allCapabilities.filter(([key]) => !isExperimental(key));
  const experimentalCapabilities = allCapabilities.filter(([key]) => isExperimental(key));

  return (
    <PageLayout title="Settings">
      {loading && <SkeletonList count={4} height="h-32" />}
      {error && <ErrorState message="Failed to load settings" detail={error} />}

      {!loading && !error && status && settings && (
        <>
          {/* Restart banner */}
          {settings.pending_restart && (
            <div className="flex items-center gap-2 rounded-lg border border-yellow-500/30 bg-yellow-500/10 p-3 text-sm text-yellow-200 mb-4">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              <span>Settings have been changed. Restart the container to apply.</span>
            </div>
          )}

          <div className="grid gap-4 md:grid-cols-2">
            {/* 1. System Overview (read-only) */}
            <Card>
              <CardHeader className="p-4 pb-2">
                <CardTitle className="flex items-center gap-2 text-sm">
                  <Database className="h-4 w-4" />
                  System Overview
                </CardTitle>
              </CardHeader>
              <CardContent className="p-4 pt-0 divide-y divide-border">
                <ReadOnlyRow label="Version" value={`v${status.version}`} />
                <ReadOnlyRow label="Status" value={status.status} />
                <ReadOnlyRow label="Memories" value={status.memories.toLocaleString()} />
                <ReadOnlyRow label="Projects" value={status.projects} />
                <ReadOnlyRow label="Transport" value={String(val("transport") ?? "")} source={src("transport")} />
                <ReadOnlyRow label="HTTP Port" value={String(val("http_port") ?? "")} source={src("http_port")} />
                <ReadOnlyRow label="CORS Origins" value={String(val("cors_origins") ?? "*")} />
                {settings.active_profile && (
                  <div className="flex items-center justify-between py-1.5 text-sm">
                    <span className="text-muted-foreground">Active Profile</span>
                    <Badge variant="secondary" className="font-mono text-xs">{settings.active_profile}</Badge>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* 1. Embedding (read-only) */}
            <Card>
              <CardHeader className="p-4 pb-2">
                <CardTitle className="flex items-center gap-2 text-sm">
                  <Layers className="h-4 w-4" />
                  Embedding
                  <Badge variant="outline" className="text-[10px] ml-auto">read-only</Badge>
                </CardTitle>
              </CardHeader>
              <CardContent className="p-4 pt-0 divide-y divide-border">
                <ReadOnlyRow label="Backend" value={String(val("embedding.backend") ?? "")} source={src("embedding.backend")} />
                <ReadOnlyRow label="Model" value={String(val("embedding.model") ?? "")} source={src("embedding.model")} />
                <ReadOnlyRow label="Dimensions" value={Number(val("embedding.dimensions") ?? 0)} source={src("embedding.dimensions")} />
                {status.models.embedding && (
                  <>
                    <ReadOnlyRow label="Calls" value={status.models.embedding.stats.calls.toLocaleString()} />
                    <ReadOnlyRow label="Health" value={status.models.embedding.health} />
                  </>
                )}
              </CardContent>
            </Card>

            {/* 2. LLM */}
            <SectionCard
              icon={<Brain className="h-4 w-4" />}
              title="LLM"
              dirty={sectionDirty("llm.") || "enrichment_enabled" in localEdits}
              onSave={() => {
                const keys = [...dirtyKeys("llm.")];
                if ("enrichment_enabled" in localEdits) keys.push("enrichment_enabled");
                saveKeys(keys, "llm.");
              }}
              saving={saving === "llm."}
            >
              <EditableSelect label="Backend" settingKey="llm.backend" value={String(val("llm.backend") ?? "ollama")} source={src("llm.backend")} options={["ollama", "bedrock", "gemini", "openai"]} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
              <EditableText label="Ollama URL" settingKey="llm.ollama_url" value={String(val("llm.ollama_url") ?? "")} source={src("llm.ollama_url")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
              <EditableText label="Ollama Model" settingKey="llm.ollama_model" value={String(val("llm.ollama_model") ?? "")} source={src("llm.ollama_model")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
              <EditableText label="Bedrock Model" settingKey="llm.bedrock_model" value={String(val("llm.bedrock_model") ?? "")} source={src("llm.bedrock_model")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
              <EditableText label="Bedrock Region" settingKey="llm.bedrock_region" value={String(val("llm.bedrock_region") ?? "")} source={src("llm.bedrock_region")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
              <EditableText label="Gemini Model" settingKey="llm.gemini_model" value={String(val("llm.gemini_model") ?? "")} source={src("llm.gemini_model")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
              <EditableText label="Gemini API Key" settingKey="llm.gemini_api_key" value={String(val("llm.gemini_api_key") ?? "")} source={src("llm.gemini_api_key")} secret localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
              <EditableText label="OpenAI URL" settingKey="llm.openai_base_url" value={String(val("llm.openai_base_url") ?? "")} source={src("llm.openai_base_url")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
              <EditableText label="OpenAI Model" settingKey="llm.openai_model" value={String(val("llm.openai_model") ?? "")} source={src("llm.openai_model")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
              <EditableText label="OpenAI API Key" settingKey="llm.openai_api_key" value={String(val("llm.openai_api_key") ?? "")} source={src("llm.openai_api_key")} secret localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
              <EditableToggle label="Enrichment" settingKey="enrichment_enabled" value={Boolean(val("enrichment_enabled"))} source={src("enrichment_enabled")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} tooltip={SETTING_TOOLTIPS.enrichment_enabled} />
            </SectionCard>

            {/* 2. Reranker */}
            <SectionCard
              icon={<Zap className="h-4 w-4" />}
              title="Reranker"
              dirty={sectionDirty("reranker.")}
              onSave={() => saveSection("reranker.")}
              saving={saving === "reranker."}
            >
              <EditableSelect label="Backend" settingKey="reranker.backend" value={String(val("reranker.backend") ?? "local")} source={src("reranker.backend")} options={["local", "bedrock"]} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
              <EditableText label="Model" settingKey="reranker.model" value={String(val("reranker.model") ?? "")} source={src("reranker.model")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
              <EditableNumber label="Candidates" settingKey="reranker.candidates" value={Number(val("reranker.candidates") ?? 50)} source={src("reranker.candidates")} min={1} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} tooltip={SETTING_TOOLTIPS["reranker.candidates"]} />
              <EditableText label="Bedrock Model" settingKey="reranker.bedrock_model" value={String(val("reranker.bedrock_model") ?? "")} source={src("reranker.bedrock_model")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
              <EditableText label="Bedrock Region" settingKey="reranker.bedrock_region" value={String(val("reranker.bedrock_region") ?? "")} source={src("reranker.bedrock_region")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
            </SectionCard>

            {/* Router — full width, 3 tiers */}
            <SectionCard
              icon={<Route className="h-4 w-4" />}
              title="Model Router"
              dirty={sectionDirty("router.")}
              onSave={() => saveSection("router.")}
              saving={saving === "router."}
              className="md:col-span-2"
            >
              <EditableToggle label="Enabled" settingKey="router.enabled" value={Boolean(val("router.enabled"))} source={src("router.enabled")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} tooltip={SETTING_TOOLTIPS["router.enabled"]} />
              {[
                { tier: "capable", label: "Capable Tier" },
                { tier: "fast", label: "Fast Tier" },
                { tier: "chat", label: "Chat Tier" },
              ].map(({ tier, label }) => (
                <div key={tier} className="pt-3">
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">{label}</h4>
                  <div className="grid gap-x-8 sm:grid-cols-3">
                    <EditableSelect label="Backend" settingKey={`router.${tier}.backend`} value={String(val(`router.${tier}.backend`) ?? "")} source={src(`router.${tier}.backend`)} options={["", "ollama", "bedrock", "gemini", "openai"]} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} tooltip={SETTING_TOOLTIPS[`router.${tier}.backend`]} />
                    <EditableText label="Model" settingKey={`router.${tier}.model`} value={String(val(`router.${tier}.model`) ?? "")} source={src(`router.${tier}.model`)} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} tooltip={SETTING_TOOLTIPS[`router.${tier}.model`]} />
                    <EditableNumber label="Daily Budget" settingKey={`router.${tier}.daily_budget`} value={Number(val(`router.${tier}.daily_budget`) ?? 0)} source={src(`router.${tier}.daily_budget`)} min={0} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} tooltip={SETTING_TOOLTIPS[`router.${tier}.daily_budget`]} />
                  </div>
                </div>
              ))}
            </SectionCard>

            {/* 3. Auth */}
            <SectionCard
              icon={<Shield className="h-4 w-4" />}
              title="Authentication"
              dirty={sectionDirty("auth.")}
              onSave={() => saveSection("auth.")}
              saving={saving === "auth."}
            >
              <EditableToggle label="Enabled" settingKey="auth.enabled" value={Boolean(val("auth.enabled"))} source={src("auth.enabled")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
              <EditableText label="API Key" settingKey="auth.api_key" value={String(val("auth.api_key") ?? "")} source={src("auth.api_key")} secret localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
              <EditableText label="Header" settingKey="auth.header_name" value={String(val("auth.header_name") ?? "X-API-Key")} source={src("auth.header_name")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
            </SectionCard>

            {/* 3. Terminal */}
            <SectionCard
              icon={<Terminal className="h-4 w-4" />}
              title="Terminal"
              dirty={sectionDirty("terminal.")}
              onSave={() => saveSection("terminal.")}
              saving={saving === "terminal."}
            >
              <EditableSelect label="Backend" settingKey="terminal.backend" value={String(val("terminal.backend") ?? "disabled")} source={src("terminal.backend")} options={["native", "ttyd", "disabled"]} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
              <EditableNumber label="Max Sessions" settingKey="terminal.max_sessions" value={Number(val("terminal.max_sessions") ?? 5)} source={src("terminal.max_sessions")} min={1} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
              <EditableNumber label="Connect Timeout" settingKey="terminal.connect_timeout" value={Number(val("terminal.connect_timeout") ?? 30)} source={src("terminal.connect_timeout")} min={1} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
            </SectionCard>

            {/* Neo4j */}
            <SectionCard
              icon={<Share2 className="h-4 w-4" />}
              title="Neo4j (Knowledge Graph)"
              dirty={sectionDirty("neo4j.")}
              onSave={() => saveSection("neo4j.")}
              saving={saving === "neo4j."}
            >
              <EditableText label="URI" settingKey="neo4j.uri" value={String(val("neo4j.uri") ?? "")} source={src("neo4j.uri")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} tooltip={SETTING_TOOLTIPS["neo4j.uri"]} />
              <EditableText label="User" settingKey="neo4j.user" value={String(val("neo4j.user") ?? "")} source={src("neo4j.user")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} tooltip={SETTING_TOOLTIPS["neo4j.user"]} />
              <EditableText label="Password" settingKey="neo4j.password" value={String(val("neo4j.password") ?? "")} source={src("neo4j.password")} secret localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} tooltip={SETTING_TOOLTIPS["neo4j.password"]} />
              <EditableText label="Database" settingKey="neo4j.database" value={String(val("neo4j.database") ?? "")} source={src("neo4j.database")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} tooltip={SETTING_TOOLTIPS["neo4j.database"]} />
            </SectionCard>

            {/* 4. Analytics */}
            <SectionCard
              icon={<BarChart3 className="h-4 w-4" />}
              title="Analytics"
              dirty={sectionDirty("analytics.")}
              onSave={() => saveSection("analytics.")}
              saving={saving === "analytics."}
            >
              <EditableToggle label="Enabled" settingKey="analytics.enabled" value={Boolean(val("analytics.enabled"))} source={src("analytics.enabled")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
              <EditableNumber label="Retention (days)" settingKey="analytics.retention_days" value={Number(val("analytics.retention_days") ?? 90)} source={src("analytics.retention_days")} min={1} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
              <EditableNumber label="Embedding $/1k" settingKey="analytics.cost_embedding_per_1k" value={Number(val("analytics.cost_embedding_per_1k") ?? 0.0001)} source={src("analytics.cost_embedding_per_1k")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} tooltip={SETTING_TOOLTIPS["analytics.cost_embedding_per_1k"]} />
              <EditableNumber label="LLM Input $/1k" settingKey="analytics.cost_llm_input_per_1k" value={Number(val("analytics.cost_llm_input_per_1k") ?? 0.003)} source={src("analytics.cost_llm_input_per_1k")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} tooltip={SETTING_TOOLTIPS["analytics.cost_llm_input_per_1k"]} />
              <EditableNumber label="LLM Output $/1k" settingKey="analytics.cost_llm_output_per_1k" value={Number(val("analytics.cost_llm_output_per_1k") ?? 0.015)} source={src("analytics.cost_llm_output_per_1k")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} tooltip={SETTING_TOOLTIPS["analytics.cost_llm_output_per_1k"]} />
            </SectionCard>

            {/* 4. Ingestion */}
            <SectionCard
              icon={<Layers className="h-4 w-4" />}
              title="Ingestion"
              dirty={"ingest_chunk_size" in localEdits || "ingest_chunk_overlap" in localEdits}
              onSave={() => {
                const keys = ["ingest_chunk_size", "ingest_chunk_overlap"].filter((k) => k in localEdits);
                saveKeys(keys, "ingest");
              }}
              saving={saving === "ingest"}
            >
              <EditableNumber label="Chunk Size (tokens)" settingKey="ingest_chunk_size" value={Number(val("ingest_chunk_size") ?? 512)} source={src("ingest_chunk_size")} min={64} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} tooltip={SETTING_TOOLTIPS.ingest_chunk_size} />
              <EditableNumber label="Chunk Overlap (tokens)" settingKey="ingest_chunk_overlap" value={Number(val("ingest_chunk_overlap") ?? 64)} source={src("ingest_chunk_overlap")} min={0} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} tooltip={SETTING_TOOLTIPS.ingest_chunk_overlap} />
            </SectionCard>

            {/* Budget (token budgets) */}
            <SectionCard
              icon={<Coins className="h-4 w-4" />}
              title="Token Budgets"
              dirty={sectionDirty("budget.")}
              onSave={() => saveSection("budget.")}
              saving={saving === "budget."}
              className="md:col-span-2"
            >
              <div className="!border-t-0">
                <div className="grid gap-x-8 sm:grid-cols-2">
                  <EditableNumber label="Rules" settingKey="budget.rules" value={Number(val("budget.rules") ?? 3000)} source={src("budget.rules")} min={0} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} tooltip={SETTING_TOOLTIPS["budget.rules"]} />
                  <EditableNumber label="Search" settingKey="budget.search" value={Number(val("budget.search") ?? 4000)} source={src("budget.search")} min={0} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} tooltip={SETTING_TOOLTIPS["budget.search"]} />
                  <EditableNumber label="Recall" settingKey="budget.recall" value={Number(val("budget.recall") ?? 8000)} source={src("budget.recall")} min={0} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} tooltip={SETTING_TOOLTIPS["budget.recall"]} />
                  <EditableNumber label="Cairn Stack" settingKey="budget.cairn_stack" value={Number(val("budget.cairn_stack") ?? 3000)} source={src("budget.cairn_stack")} min={0} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} tooltip={SETTING_TOOLTIPS["budget.cairn_stack"]} />
                  <EditableNumber label="Insights" settingKey="budget.insights" value={Number(val("budget.insights") ?? 4000)} source={src("budget.insights")} min={0} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} tooltip={SETTING_TOOLTIPS["budget.insights"]} />
                  <EditableNumber label="Workspace" settingKey="budget.workspace" value={Number(val("budget.workspace") ?? 6000)} source={src("budget.workspace")} min={0} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} tooltip={SETTING_TOOLTIPS["budget.workspace"]} />
                </div>
              </div>
            </SectionCard>

            {/* 5. LLM Capabilities — full width, stable/experimental split */}
            <SectionCard
              icon={<Cpu className="h-4 w-4" />}
              title="LLM Capabilities"
              dirty={sectionDirty("capabilities.")}
              onSave={() => saveSection("capabilities.")}
              saving={saving === "capabilities."}
              className="md:col-span-2"
            >
              {/* Stable section */}
              <div className="!border-t-0 pb-4">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">Stable</h4>
                <div className="grid gap-x-8 sm:grid-cols-2">
                  {stableCapabilities.map(([key, meta]) => (
                    <EditableToggle
                      key={key}
                      label={meta.label}
                      settingKey={`capabilities.${key}`}
                      value={Boolean(val(`capabilities.${key}`))}
                      source={src(`capabilities.${key}`)}
                      localEdits={localEdits}
                      setLocalEdits={setLocalEdits}
                      onReset={handleReset}
                      tooltip={meta.description}
                    />
                  ))}
                </div>
              </div>

              {/* Experimental section */}
              {experimentalCapabilities.length > 0 && (
                <div className="border-t border-amber-500/25 pt-4">
                  <div className="flex items-center gap-2 mb-1">
                    <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Experimental</h4>
                    <Badge variant="experimental" className="text-[10px]">experimental</Badge>
                  </div>
                  <p className="text-xs text-muted-foreground mb-3">May change behavior between releases.</p>
                  <div className="grid gap-x-8 sm:grid-cols-2">
                    {experimentalCapabilities.map(([key, meta]) => (
                      <EditableToggle
                        key={key}
                        label={meta.label}
                        settingKey={`capabilities.${key}`}
                        value={Boolean(val(`capabilities.${key}`))}
                        source={src(`capabilities.${key}`)}
                        localEdits={localEdits}
                        setLocalEdits={setLocalEdits}
                        onReset={handleReset}
                        tooltip={meta.description}
                      />
                    ))}
                  </div>
                </div>
              )}
            </SectionCard>

            {/* 6. Database (read-only) */}
            <Card>
              <CardHeader className="p-4 pb-2">
                <CardTitle className="flex items-center gap-2 text-sm">
                  <Database className="h-4 w-4" />
                  Database
                  <Badge variant="outline" className="text-[10px] ml-auto">read-only</Badge>
                </CardTitle>
              </CardHeader>
              <CardContent className="p-4 pt-0 divide-y divide-border">
                <ReadOnlyRow label="Host" value={String(val("db.host") ?? "")} source={src("db.host")} />
                <ReadOnlyRow label="Port" value={Number(val("db.port") ?? 0)} source={src("db.port")} />
                <ReadOnlyRow label="Name" value={String(val("db.name") ?? "")} source={src("db.name")} />
                <ReadOnlyRow label="User" value={String(val("db.user") ?? "")} source={src("db.user")} />
              </CardContent>
            </Card>

            {/* 6. Memory Types */}
            <Card>
              <CardHeader className="p-4 pb-2">
                <CardTitle className="flex items-center gap-2 text-sm">
                  <Layers className="h-4 w-4" />
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
        </>
      )}
    </PageLayout>
  );
}
