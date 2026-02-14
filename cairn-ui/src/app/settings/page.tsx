"use client";

import { useEffect, useState, useCallback } from "react";
import { api, type Status, type SettingsResponse } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ErrorState } from "@/components/error-state";
import { SkeletonList } from "@/components/skeleton-list";
import { PageLayout } from "@/components/page-layout";
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

// --- Field types ---

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

const SECRET_KEYS = new Set([
  "llm.gemini_api_key", "llm.openai_api_key",
  "auth.api_key", "terminal.encryption_key",
  "db.password", "embedding.openai_api_key",
  "workspace.password",
]);

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
  label, settingKey, value, source, secret, localEdits, setLocalEdits, onReset,
}: {
  label: string; settingKey: string; value: string; source: "default" | "env" | "db";
  secret?: boolean; localEdits: Record<string, string>; setLocalEdits: (e: Record<string, string>) => void;
  onReset: (key: string) => void;
}) {
  const [show, setShow] = useState(false);
  const editedValue = settingKey in localEdits ? localEdits[settingKey] : value;
  const isSecret = secret || SECRET_KEYS.has(settingKey);

  return (
    <div className="flex items-center justify-between gap-3 py-1.5 text-sm">
      <div className="flex items-center gap-2 shrink-0">
        <span className="text-muted-foreground">{label}</span>
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
  label, settingKey, value, source, localEdits, setLocalEdits, onReset, min,
}: {
  label: string; settingKey: string; value: number; source: "default" | "env" | "db";
  localEdits: Record<string, string>; setLocalEdits: (e: Record<string, string>) => void;
  onReset: (key: string) => void; min?: number;
}) {
  const editedValue = settingKey in localEdits ? localEdits[settingKey] : String(value);

  return (
    <div className="flex items-center justify-between gap-3 py-1.5 text-sm">
      <div className="flex items-center gap-2 shrink-0">
        <span className="text-muted-foreground">{label}</span>
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
  label, settingKey, value, source, localEdits, setLocalEdits, onReset,
}: {
  label: string; settingKey: string; value: boolean; source: "default" | "env" | "db";
  localEdits: Record<string, string>; setLocalEdits: (e: Record<string, string>) => void;
  onReset: (key: string) => void;
}) {
  const editedValue = settingKey in localEdits
    ? localEdits[settingKey] === "true"
    : value;

  return (
    <div className="flex items-center justify-between py-1.5 text-sm">
      <div className="flex items-center gap-2">
        <span className={editedValue ? "" : "text-muted-foreground"}>{label}</span>
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
  label, settingKey, value, source, options, localEdits, setLocalEdits, onReset,
}: {
  label: string; settingKey: string; value: string; source: "default" | "env" | "db";
  options: string[]; localEdits: Record<string, string>; setLocalEdits: (e: Record<string, string>) => void;
  onReset: (key: string) => void;
}) {
  const editedValue = settingKey in localEdits ? localEdits[settingKey] : value;

  return (
    <div className="flex items-center justify-between gap-3 py-1.5 text-sm">
      <div className="flex items-center gap-2 shrink-0">
        <span className="text-muted-foreground">{label}</span>
        <SourceBadge source={source} />
        {source === "db" && (
          <button onClick={() => onReset(settingKey)} className="text-muted-foreground hover:text-foreground" title="Reset to default">
            <RotateCcw className="h-3 w-3" />
          </button>
        )}
      </div>
      <select
        value={editedValue}
        onChange={(e) => setLocalEdits({ ...localEdits, [settingKey]: e.target.value })}
        className="h-7 rounded-md border border-input bg-transparent px-2 text-xs font-mono outline-none focus:ring-2 focus:ring-ring"
      >
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
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
            {/* System Overview (read-only) */}
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
              </CardContent>
            </Card>

            {/* Embedding (read-only — changing would invalidate vectors) */}
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

            {/* LLM */}
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
              <EditableToggle label="Enrichment" settingKey="enrichment_enabled" value={Boolean(val("enrichment_enabled"))} source={src("enrichment_enabled")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
            </SectionCard>

            {/* Reranker */}
            <SectionCard
              icon={<Zap className="h-4 w-4" />}
              title="Reranker"
              dirty={sectionDirty("reranker.")}
              onSave={() => saveSection("reranker.")}
              saving={saving === "reranker."}
            >
              <EditableSelect label="Backend" settingKey="reranker.backend" value={String(val("reranker.backend") ?? "local")} source={src("reranker.backend")} options={["local", "bedrock"]} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
              <EditableText label="Model" settingKey="reranker.model" value={String(val("reranker.model") ?? "")} source={src("reranker.model")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
              <EditableNumber label="Candidates" settingKey="reranker.candidates" value={Number(val("reranker.candidates") ?? 50)} source={src("reranker.candidates")} min={1} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
              <EditableText label="Bedrock Model" settingKey="reranker.bedrock_model" value={String(val("reranker.bedrock_model") ?? "")} source={src("reranker.bedrock_model")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
              <EditableText label="Bedrock Region" settingKey="reranker.bedrock_region" value={String(val("reranker.bedrock_region") ?? "")} source={src("reranker.bedrock_region")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
            </SectionCard>

            {/* Auth */}
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

            {/* Terminal */}
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

            {/* Analytics */}
            <SectionCard
              icon={<BarChart3 className="h-4 w-4" />}
              title="Analytics"
              dirty={sectionDirty("analytics.")}
              onSave={() => saveSection("analytics.")}
              saving={saving === "analytics."}
            >
              <EditableToggle label="Enabled" settingKey="analytics.enabled" value={Boolean(val("analytics.enabled"))} source={src("analytics.enabled")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
              <EditableNumber label="Retention (days)" settingKey="analytics.retention_days" value={Number(val("analytics.retention_days") ?? 90)} source={src("analytics.retention_days")} min={1} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
              <EditableNumber label="Embedding $/1k" settingKey="analytics.cost_embedding_per_1k" value={Number(val("analytics.cost_embedding_per_1k") ?? 0.0001)} source={src("analytics.cost_embedding_per_1k")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
              <EditableNumber label="LLM Input $/1k" settingKey="analytics.cost_llm_input_per_1k" value={Number(val("analytics.cost_llm_input_per_1k") ?? 0.003)} source={src("analytics.cost_llm_input_per_1k")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
              <EditableNumber label="LLM Output $/1k" settingKey="analytics.cost_llm_output_per_1k" value={Number(val("analytics.cost_llm_output_per_1k") ?? 0.015)} source={src("analytics.cost_llm_output_per_1k")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
            </SectionCard>

            {/* Ingestion */}
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
              <EditableNumber label="Chunk Size (tokens)" settingKey="ingest_chunk_size" value={Number(val("ingest_chunk_size") ?? 512)} source={src("ingest_chunk_size")} min={64} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
              <EditableNumber label="Chunk Overlap (tokens)" settingKey="ingest_chunk_overlap" value={Number(val("ingest_chunk_overlap") ?? 64)} source={src("ingest_chunk_overlap")} min={0} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
            </SectionCard>

            {/* LLM Capabilities — full width */}
            <SectionCard
              icon={<Cpu className="h-4 w-4" />}
              title="LLM Capabilities"
              dirty={sectionDirty("capabilities.")}
              onSave={() => saveSection("capabilities.")}
              saving={saving === "capabilities."}
              className="md:col-span-2"
            >
              <div className="grid gap-x-8 sm:grid-cols-2 lg:grid-cols-3 !divide-y-0">
                {Object.entries(CAPABILITY_LABELS).map(([key, label]) => (
                  <EditableToggle
                    key={key}
                    label={label}
                    settingKey={`capabilities.${key}`}
                    value={Boolean(val(`capabilities.${key}`))}
                    source={src(`capabilities.${key}`)}
                    localEdits={localEdits}
                    setLocalEdits={setLocalEdits}
                    onReset={handleReset}
                  />
                ))}
              </div>
            </SectionCard>

            {/* Database (read-only) */}
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

            {/* Memory Types */}
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
