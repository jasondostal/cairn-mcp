"use client";

import type { Status, SettingsResponse } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Cpu,
  Database,
  Brain,
  Shield,
  BarChart3,
  Terminal,
  Layers,
  Zap,
  Route,
  Share2,
  Coins,
  Eye,
  Globe,
  Bell,
  Timer,
  Activity,
  Boxes,
  Clock,
  Network,
} from "lucide-react";
import {
  ReadOnlyRow,
  SectionCard,
  EditableText,
  EditableNumber,
  EditableToggle,
  EditableSelect,
  CAPABILITY_META,
  SETTING_TOOLTIPS,
} from "./setting-primitives";

// --- Props shared by all section components ---

export interface SettingsSectionProps {
  status: Status;
  settings: SettingsResponse;
  localEdits: Record<string, string>;
  setLocalEdits: (e: Record<string, string>) => void;
  saving: string | null;
  sectionVisible: (prefix: string, ...extraKeys: string[]) => boolean;
  sectionDirty: (prefix: string) => boolean;
  dirtyKeys: (prefix: string) => string[];
  saveSection: (prefix: string) => void;
  saveKeys: (keys: string[], savingId: string) => void;
  handleReset: (key: string) => void;
  val: (key: string) => unknown;
  src: (key: string) => "default" | "env" | "db";
  isEnvLocked: (key: string) => boolean;
  isExperimental: (key: string) => boolean;
}

// --- System Overview (read-only) ---

export function SystemOverviewSection({ status, settings, val, src }: SettingsSectionProps) {
  return (
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
  );
}

// --- Embedding (read-only) ---

export function EmbeddingSection({ status, val, src }: SettingsSectionProps) {
  return (
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
  );
}

// --- LLM ---

export function LLMSection({ localEdits, setLocalEdits, saving, sectionVisible, sectionDirty, dirtyKeys, saveKeys, handleReset, val, src }: SettingsSectionProps) {
  if (!sectionVisible("llm.", "enrichment_enabled")) return null;
  return (
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
  );
}

// --- Reranker ---

export function RerankerSection({ localEdits, setLocalEdits, saving, sectionVisible, sectionDirty, saveSection, handleReset, val, src }: SettingsSectionProps) {
  if (!sectionVisible("reranker.")) return null;
  return (
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
  );
}

// --- Model Router ---

export function RouterSection({ localEdits, setLocalEdits, saving, sectionVisible, sectionDirty, saveSection, handleReset, val, src }: SettingsSectionProps) {
  if (!sectionVisible("router.")) return null;
  return (
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
  );
}

// --- Auth ---

export function AuthSection({ localEdits, setLocalEdits, saving, sectionVisible, sectionDirty, saveSection, handleReset, val, src }: SettingsSectionProps) {
  if (!sectionVisible("auth.")) return null;
  return (
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
  );
}

// --- Terminal ---

export function TerminalSection({ localEdits, setLocalEdits, saving, sectionVisible, sectionDirty, saveSection, handleReset, val, src }: SettingsSectionProps) {
  if (!sectionVisible("terminal.")) return null;
  return (
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
  );
}

// --- Neo4j ---

export function Neo4jSection({ localEdits, setLocalEdits, saving, sectionVisible, sectionDirty, saveSection, handleReset, val, src }: SettingsSectionProps) {
  if (!sectionVisible("neo4j.")) return null;
  return (
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
  );
}

// --- Analytics ---

export function AnalyticsSection({ localEdits, setLocalEdits, saving, sectionVisible, sectionDirty, saveSection, handleReset, val, src }: SettingsSectionProps) {
  if (!sectionVisible("analytics.")) return null;
  return (
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
  );
}

// --- Ingestion ---

export function IngestionSection({ localEdits, setLocalEdits, saving, sectionVisible, saveKeys, handleReset, val, src }: SettingsSectionProps) {
  if (!sectionVisible("ingest")) return null;
  return (
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
  );
}

// --- Token Budgets ---

export function BudgetSection({ localEdits, setLocalEdits, saving, sectionVisible, sectionDirty, saveSection, handleReset, val, src }: SettingsSectionProps) {
  if (!sectionVisible("budget.")) return null;
  return (
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
  );
}

// --- LLM Capabilities ---

export function CapabilitiesSection({ localEdits, setLocalEdits, saving, sectionVisible, sectionDirty, saveSection, handleReset, val, src, isExperimental }: SettingsSectionProps) {
  if (!sectionVisible("capabilities.")) return null;

  const allCapabilities = Object.entries(CAPABILITY_META);
  const stableCapabilities = allCapabilities.filter(([key]) => !isExperimental(key));
  const experimentalCapabilities = allCapabilities.filter(([key]) => isExperimental(key));

  return (
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
  );
}

// --- Audit Trail ---

export function AuditSection({ localEdits, setLocalEdits, saving, sectionVisible, sectionDirty, saveSection, handleReset, val, src, isEnvLocked }: SettingsSectionProps) {
  if (!sectionVisible("audit.")) return null;
  return (
    <SectionCard
      icon={<Eye className="h-4 w-4" />}
      title="Audit Trail"
      dirty={sectionDirty("audit.")}
      onSave={() => saveSection("audit.")}
      saving={saving === "audit."}
    >
      <EditableToggle label="Enabled" settingKey="audit.enabled" value={Boolean(val("audit.enabled"))} source={src("audit.enabled")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("audit.enabled")} />
    </SectionCard>
  );
}

// --- Webhooks ---

export function WebhooksSection({ localEdits, setLocalEdits, saving, sectionVisible, sectionDirty, saveSection, handleReset, val, src, isEnvLocked }: SettingsSectionProps) {
  if (!sectionVisible("webhooks.")) return null;
  return (
    <SectionCard
      icon={<Globe className="h-4 w-4" />}
      title="Webhooks"
      dirty={sectionDirty("webhooks.")}
      onSave={() => saveSection("webhooks.")}
      saving={saving === "webhooks."}
    >
      <EditableToggle label="Enabled" settingKey="webhooks.enabled" value={Boolean(val("webhooks.enabled"))} source={src("webhooks.enabled")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("webhooks.enabled")} />
      <EditableNumber label="Delivery Interval (s)" settingKey="webhooks.delivery_interval" value={Number(val("webhooks.delivery_interval") ?? 5)} source={src("webhooks.delivery_interval")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("webhooks.delivery_interval")} />
      <EditableNumber label="Batch Size" settingKey="webhooks.delivery_batch_size" value={Number(val("webhooks.delivery_batch_size") ?? 20)} source={src("webhooks.delivery_batch_size")} min={1} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("webhooks.delivery_batch_size")} />
      <EditableNumber label="Max Attempts" settingKey="webhooks.max_attempts" value={Number(val("webhooks.max_attempts") ?? 5)} source={src("webhooks.max_attempts")} min={1} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("webhooks.max_attempts")} />
      <EditableNumber label="Backoff Base (s)" settingKey="webhooks.backoff_base" value={Number(val("webhooks.backoff_base") ?? 30)} source={src("webhooks.backoff_base")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("webhooks.backoff_base")} />
      <EditableNumber label="Timeout (s)" settingKey="webhooks.timeout" value={Number(val("webhooks.timeout") ?? 10)} source={src("webhooks.timeout")} min={1} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("webhooks.timeout")} />
    </SectionCard>
  );
}

// --- Alerting ---

export function AlertingSection({ localEdits, setLocalEdits, saving, sectionVisible, sectionDirty, saveSection, handleReset, val, src, isEnvLocked }: SettingsSectionProps) {
  if (!sectionVisible("alerting.")) return null;
  return (
    <SectionCard
      icon={<Bell className="h-4 w-4" />}
      title="Alerting"
      dirty={sectionDirty("alerting.")}
      onSave={() => saveSection("alerting.")}
      saving={saving === "alerting."}
    >
      <EditableToggle label="Enabled" settingKey="alerting.enabled" value={Boolean(val("alerting.enabled"))} source={src("alerting.enabled")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("alerting.enabled")} />
      <EditableNumber label="Eval Interval (s)" settingKey="alerting.eval_interval_seconds" value={Number(val("alerting.eval_interval_seconds") ?? 60)} source={src("alerting.eval_interval_seconds")} min={1} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("alerting.eval_interval_seconds")} />
    </SectionCard>
  );
}

// --- Retention ---

export function RetentionSection({ localEdits, setLocalEdits, saving, sectionVisible, sectionDirty, saveSection, handleReset, val, src, isEnvLocked }: SettingsSectionProps) {
  if (!sectionVisible("retention.")) return null;
  return (
    <SectionCard
      icon={<Timer className="h-4 w-4" />}
      title="Retention"
      dirty={sectionDirty("retention.")}
      onSave={() => saveSection("retention.")}
      saving={saving === "retention."}
    >
      <EditableToggle label="Enabled" settingKey="retention.enabled" value={Boolean(val("retention.enabled"))} source={src("retention.enabled")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("retention.enabled")} />
      <EditableNumber label="Scan Interval (h)" settingKey="retention.scan_interval_hours" value={Number(val("retention.scan_interval_hours") ?? 24)} source={src("retention.scan_interval_hours")} min={1} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("retention.scan_interval_hours")} />
      <EditableToggle label="Dry Run" settingKey="retention.dry_run" value={Boolean(val("retention.dry_run") ?? true)} source={src("retention.dry_run")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("retention.dry_run")} />
    </SectionCard>
  );
}

// --- OpenTelemetry ---

export function OtelSection({ localEdits, setLocalEdits, saving, sectionVisible, sectionDirty, saveSection, handleReset, val, src, isEnvLocked }: SettingsSectionProps) {
  if (!sectionVisible("otel.")) return null;
  return (
    <SectionCard
      icon={<Activity className="h-4 w-4" />}
      title="OpenTelemetry"
      dirty={sectionDirty("otel.")}
      onSave={() => saveSection("otel.")}
      saving={saving === "otel."}
    >
      <EditableToggle label="Enabled" settingKey="otel.enabled" value={Boolean(val("otel.enabled"))} source={src("otel.enabled")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("otel.enabled")} />
      <EditableText label="Endpoint" settingKey="otel.endpoint" value={String(val("otel.endpoint") ?? "")} source={src("otel.endpoint")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("otel.endpoint")} />
      <EditableText label="Service Name" settingKey="otel.service_name" value={String(val("otel.service_name") ?? "cairn")} source={src("otel.service_name")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("otel.service_name")} />
    </SectionCard>
  );
}

// --- Workspace ---

export function WorkspaceSection({ localEdits, setLocalEdits, saving, sectionVisible, sectionDirty, saveSection, handleReset, val, src, isEnvLocked }: SettingsSectionProps) {
  if (!sectionVisible("workspace.")) return null;
  return (
    <SectionCard
      icon={<Boxes className="h-4 w-4" />}
      title="Workspace"
      dirty={sectionDirty("workspace.")}
      onSave={() => saveSection("workspace.")}
      saving={saving === "workspace."}
      className="md:col-span-2"
    >
      <EditableSelect label="Default Backend" settingKey="workspace.default_backend" value={String(val("workspace.default_backend") ?? "opencode")} source={src("workspace.default_backend")} options={["opencode", "claude_code"]} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("workspace.default_backend")} />
      <EditableText label="URL" settingKey="workspace.url" value={String(val("workspace.url") ?? "")} source={src("workspace.url")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("workspace.url")} />
      <EditableText label="Password" settingKey="workspace.password" value={String(val("workspace.password") ?? "")} source={src("workspace.password")} secret localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("workspace.password")} />
      <EditableText label="Default Agent" settingKey="workspace.default_agent" value={String(val("workspace.default_agent") ?? "")} source={src("workspace.default_agent")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("workspace.default_agent")} />
      <EditableToggle label="Claude Code Enabled" settingKey="workspace.claude_code_enabled" value={Boolean(val("workspace.claude_code_enabled"))} source={src("workspace.claude_code_enabled")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("workspace.claude_code_enabled")} />
      <EditableText label="CC Working Dir" settingKey="workspace.claude_code_working_dir" value={String(val("workspace.claude_code_working_dir") ?? "")} source={src("workspace.claude_code_working_dir")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("workspace.claude_code_working_dir")} />
      <EditableNumber label="CC Max Turns" settingKey="workspace.claude_code_max_turns" value={Number(val("workspace.claude_code_max_turns") ?? 25)} source={src("workspace.claude_code_max_turns")} min={1} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("workspace.claude_code_max_turns")} />
      <EditableNumber label="CC Max Budget ($)" settingKey="workspace.claude_code_max_budget" value={Number(val("workspace.claude_code_max_budget") ?? 10)} source={src("workspace.claude_code_max_budget")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("workspace.claude_code_max_budget")} />
      <EditableText label="CC MCP URL" settingKey="workspace.claude_code_mcp_url" value={String(val("workspace.claude_code_mcp_url") ?? "")} source={src("workspace.claude_code_mcp_url")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("workspace.claude_code_mcp_url")} />
      <EditableText label="CC SSH Host" settingKey="workspace.claude_code_ssh_host" value={String(val("workspace.claude_code_ssh_host") ?? "")} source={src("workspace.claude_code_ssh_host")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("workspace.claude_code_ssh_host")} />
      <EditableText label="CC SSH User" settingKey="workspace.claude_code_ssh_user" value={String(val("workspace.claude_code_ssh_user") ?? "")} source={src("workspace.claude_code_ssh_user")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("workspace.claude_code_ssh_user")} />
      <EditableText label="CC SSH Key" settingKey="workspace.claude_code_ssh_key" value={String(val("workspace.claude_code_ssh_key") ?? "")} source={src("workspace.claude_code_ssh_key")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("workspace.claude_code_ssh_key")} />
    </SectionCard>
  );
}

// --- OIDC ---

export function OIDCSection({ localEdits, setLocalEdits, saving, sectionVisible, sectionDirty, saveSection, handleReset, val, src, isEnvLocked }: SettingsSectionProps) {
  if (!sectionVisible("auth.oidc.")) return null;
  return (
    <SectionCard
      icon={<Shield className="h-4 w-4" />}
      title="OIDC / SSO"
      dirty={sectionDirty("auth.oidc.")}
      onSave={() => saveSection("auth.oidc.")}
      saving={saving === "auth.oidc."}
    >
      <EditableToggle label="Enabled" settingKey="auth.oidc.enabled" value={Boolean(val("auth.oidc.enabled"))} source={src("auth.oidc.enabled")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("auth.oidc.enabled")} />
      <EditableText label="Provider URL" settingKey="auth.oidc.provider_url" value={String(val("auth.oidc.provider_url") ?? "")} source={src("auth.oidc.provider_url")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("auth.oidc.provider_url")} />
      <EditableText label="Scopes" settingKey="auth.oidc.scopes" value={String(val("auth.oidc.scopes") ?? "openid profile email")} source={src("auth.oidc.scopes")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("auth.oidc.scopes")} />
      <EditableToggle label="Auto-Create Users" settingKey="auth.oidc.auto_create_users" value={Boolean(val("auth.oidc.auto_create_users") ?? true)} source={src("auth.oidc.auto_create_users")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("auth.oidc.auto_create_users")} />
      <EditableText label="Default Role" settingKey="auth.oidc.default_role" value={String(val("auth.oidc.default_role") ?? "user")} source={src("auth.oidc.default_role")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("auth.oidc.default_role")} />
      <EditableText label="Admin Groups" settingKey="auth.oidc.admin_groups" value={String(val("auth.oidc.admin_groups") ?? "")} source={src("auth.oidc.admin_groups")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("auth.oidc.admin_groups")} />
    </SectionCard>
  );
}

// --- Decay ---

export function DecaySection({ localEdits, setLocalEdits, saving, sectionVisible, sectionDirty, saveSection, handleReset, val, src, isEnvLocked }: SettingsSectionProps) {
  if (!sectionVisible("decay.")) return null;
  return (
    <SectionCard
      icon={<Clock className="h-4 w-4" />}
      title="Decay (Controlled Forgetting)"
      dirty={sectionDirty("decay.")}
      onSave={() => saveSection("decay.")}
      saving={saving === "decay."}
    >
      <EditableToggle label="Enabled" settingKey="decay.enabled" value={Boolean(val("decay.enabled"))} source={src("decay.enabled")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("decay.enabled")} />
      <EditableNumber label="Scan Interval (h)" settingKey="decay.scan_interval_hours" value={Number(val("decay.scan_interval_hours") ?? 24)} source={src("decay.scan_interval_hours")} min={1} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("decay.scan_interval_hours")} />
      <EditableNumber label="Threshold" settingKey="decay.threshold" value={Number(val("decay.threshold") ?? 0.05)} source={src("decay.threshold")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("decay.threshold")} />
      <EditableNumber label="Min Age (days)" settingKey="decay.min_age_days" value={Number(val("decay.min_age_days") ?? 90)} source={src("decay.min_age_days")} min={0} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("decay.min_age_days")} />
      <EditableNumber label="Protect Importance" settingKey="decay.protect_importance" value={Number(val("decay.protect_importance") ?? 0.8)} source={src("decay.protect_importance")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("decay.protect_importance")} />
      <EditableToggle label="Dry Run" settingKey="decay.dry_run" value={Boolean(val("decay.dry_run") ?? true)} source={src("decay.dry_run")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("decay.dry_run")} />
    </SectionCard>
  );
}

// --- Clustering ---

export function ClusteringSection({ localEdits, setLocalEdits, saving, sectionVisible, sectionDirty, saveSection, handleReset, val, src, isEnvLocked }: SettingsSectionProps) {
  if (!sectionVisible("clustering.")) return null;
  return (
    <SectionCard
      icon={<Network className="h-4 w-4" />}
      title="Clustering"
      dirty={sectionDirty("clustering.")}
      onSave={() => saveSection("clustering.")}
      saving={saving === "clustering."}
    >
      <EditableNumber label="Min Cluster Size" settingKey="clustering.min_cluster_size" value={Number(val("clustering.min_cluster_size") ?? 3)} source={src("clustering.min_cluster_size")} min={2} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("clustering.min_cluster_size")} />
      <EditableNumber label="Min Samples" settingKey="clustering.min_samples" value={Number(val("clustering.min_samples") ?? 2)} source={src("clustering.min_samples")} min={1} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("clustering.min_samples")} />
      <EditableSelect label="Selection Method" settingKey="clustering.selection_method" value={String(val("clustering.selection_method") ?? "leaf")} source={src("clustering.selection_method")} options={["eom", "leaf"]} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("clustering.selection_method")} />
      <EditableNumber label="Staleness (h)" settingKey="clustering.staleness_hours" value={Number(val("clustering.staleness_hours") ?? 24)} source={src("clustering.staleness_hours")} min={1} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("clustering.staleness_hours")} />
      <EditableNumber label="Staleness Growth (%)" settingKey="clustering.staleness_growth_pct" value={Number(val("clustering.staleness_growth_pct") ?? 20)} source={src("clustering.staleness_growth_pct")} min={1} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("clustering.staleness_growth_pct")} />
    </SectionCard>
  );
}

// --- Database (read-only) ---

export function DatabaseSection({ val, src }: SettingsSectionProps) {
  return (
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
  );
}

// --- Memory Types ---

export function MemoryTypesSection({ status }: SettingsSectionProps) {
  return (
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
  );
}
