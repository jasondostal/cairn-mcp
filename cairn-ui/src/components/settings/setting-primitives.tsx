"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SingleSelect } from "@/components/ui/single-select";
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import {
  Save,
  RotateCcw,
  Eye,
  EyeOff,
  CircleHelp,
  Lock,
} from "lucide-react";

// --- Constants ---

export interface CapabilityMeta { label: string; description: string; }

export const CAPABILITY_META: Record<string, CapabilityMeta> = {
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

export const SECRET_KEYS = new Set([
  "llm.gemini_api_key", "llm.openai_api_key",
  "auth.api_key", "terminal.encryption_key",
  "db.password", "embedding.openai_api_key",
  "workspace.password", "neo4j.password",
]);

export const SETTING_TOOLTIPS: Record<string, string> = {
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

// --- Shared editable field props ---

export interface EditableFieldProps {
  localEdits: Record<string, string>;
  setLocalEdits: (e: Record<string, string>) => void;
  onReset: (key: string) => void;
  tooltip?: string;
  envLocked?: boolean;
}

// --- Source badge ---

export function SourceBadge({ source }: { source: "default" | "env" | "db" }) {
  const variants: Record<string, { variant: "default" | "secondary" | "outline"; label: string }> = {
    default: { variant: "outline", label: "default" },
    env: { variant: "secondary", label: "env" },
    db: { variant: "default", label: "db" },
  };
  const { variant, label } = variants[source] || variants.default;
  return <Badge variant={variant} className="text-[10px] px-1.5 py-0">{label}</Badge>;
}

// --- Env-locked badge ---

export function EnvLockedBadge() {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge variant="secondary" className="text-[10px] px-1.5 py-0 gap-0.5">
          <Lock className="h-2.5 w-2.5" />
          env-locked
        </Badge>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-[240px]">
        <p>This setting is locked by an environment variable and cannot be changed via the UI.</p>
      </TooltipContent>
    </Tooltip>
  );
}

// --- Tooltip label helper ---

export function TooltipLabel({ children, description }: { children: React.ReactNode; description?: string }) {
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

export function Toggle({
  checked, onChange, disabled, label,
}: { checked: boolean; onChange: (v: boolean) => void; disabled?: boolean; label?: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
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

export function ReadOnlyRow({ label, value, source }: { label: string; value: string | number | boolean; source?: "default" | "env" | "db" }) {
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

export interface SectionProps {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
  dirty: boolean;
  onSave: () => void;
  saving: boolean;
  className?: string;
}

export function SectionCard({ icon, title, children, dirty, onSave, saving, className }: SectionProps) {
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

export function EditableText({
  label, settingKey, value, source, secret, localEdits, setLocalEdits, onReset, tooltip, envLocked,
}: {
  label: string; settingKey: string; value: string; source: "default" | "env" | "db";
  secret?: boolean;
} & EditableFieldProps) {
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
        {envLocked ? <EnvLockedBadge /> : <SourceBadge source={source} />}
        {!envLocked && source === "db" && (
          <button onClick={() => onReset(settingKey)} className="text-muted-foreground hover:text-foreground" title="Reset to default">
            <RotateCcw className="h-3 w-3" />
          </button>
        )}
      </div>
      <div className="flex items-center gap-1.5 min-w-0 max-w-[280px]">
        <Input
          type={isSecret && !show ? "password" : "text"}
          value={editedValue}
          disabled={envLocked}
          onChange={(e) => setLocalEdits({ ...localEdits, [settingKey]: e.target.value })}
          className="h-7 text-xs font-mono"
          aria-label={label}
        />
        {isSecret && !envLocked && (
          <button onClick={() => setShow(!show)} className="text-muted-foreground hover:text-foreground shrink-0">
            {show ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
          </button>
        )}
      </div>
    </div>
  );
}

export function EditableNumber({
  label, settingKey, value, source, localEdits, setLocalEdits, onReset, min, tooltip, envLocked,
}: {
  label: string; settingKey: string; value: number; source: "default" | "env" | "db";
  min?: number;
} & EditableFieldProps) {
  const editedValue = settingKey in localEdits ? localEdits[settingKey] : String(value);
  const dirty = settingKey in localEdits;

  return (
    <div className={cn("flex items-center justify-between gap-3 py-1.5 text-sm", dirty && "bg-primary/5 rounded-sm px-2 -mx-2")}>
      <div className="flex items-center gap-2 shrink-0">
        {dirty && <span className="size-1 rounded-full bg-primary" />}
        <TooltipLabel description={tooltip}>
          <span className="text-muted-foreground">{label}</span>
        </TooltipLabel>
        {envLocked ? <EnvLockedBadge /> : <SourceBadge source={source} />}
        {!envLocked && source === "db" && (
          <button onClick={() => onReset(settingKey)} className="text-muted-foreground hover:text-foreground" title="Reset to default">
            <RotateCcw className="h-3 w-3" />
          </button>
        )}
      </div>
      <Input
        type="number"
        value={editedValue}
        min={min ?? 0}
        disabled={envLocked}
        onChange={(e) => setLocalEdits({ ...localEdits, [settingKey]: e.target.value })}
        className="h-7 text-xs font-mono w-24"
        aria-label={label}
      />
    </div>
  );
}

export function EditableToggle({
  label, settingKey, value, source, localEdits, setLocalEdits, onReset, tooltip, envLocked,
}: {
  label: string; settingKey: string; value: boolean; source: "default" | "env" | "db";
} & EditableFieldProps) {
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
        {envLocked ? <EnvLockedBadge /> : <SourceBadge source={source} />}
        {!envLocked && source === "db" && (
          <button onClick={() => onReset(settingKey)} className="text-muted-foreground hover:text-foreground" title="Reset to default">
            <RotateCcw className="h-3 w-3" />
          </button>
        )}
      </div>
      <Toggle
        checked={editedValue}
        onChange={(v) => setLocalEdits({ ...localEdits, [settingKey]: v ? "true" : "false" })}
        disabled={envLocked}
        label={label}
      />
    </div>
  );
}

export function EditableSelect({
  label, settingKey, value, source, options, localEdits, setLocalEdits, onReset, tooltip, envLocked,
}: {
  label: string; settingKey: string; value: string; source: "default" | "env" | "db";
  options: string[];
} & EditableFieldProps) {
  const editedValue = settingKey in localEdits ? localEdits[settingKey] : value;
  const dirty = settingKey in localEdits;

  return (
    <div className={cn("flex items-center justify-between gap-3 py-1.5 text-sm", dirty && "bg-primary/5 rounded-sm px-2 -mx-2")}>
      <div className="flex items-center gap-2 shrink-0">
        {dirty && <span className="size-1 rounded-full bg-primary" />}
        <TooltipLabel description={tooltip}>
          <span className="text-muted-foreground">{label}</span>
        </TooltipLabel>
        {envLocked ? <EnvLockedBadge /> : <SourceBadge source={source} />}
        {!envLocked && source === "db" && (
          <button onClick={() => onReset(settingKey)} className="text-muted-foreground hover:text-foreground" title="Reset to default">
            <RotateCcw className="h-3 w-3" />
          </button>
        )}
      </div>
      <SingleSelect
        options={options.map((o) => ({ value: o, label: o }))}
        value={editedValue}
        onValueChange={(v) => setLocalEdits({ ...localEdits, [settingKey]: v })}
        disabled={envLocked}
        className="h-7 text-xs font-mono"
      />
    </div>
  );
}
