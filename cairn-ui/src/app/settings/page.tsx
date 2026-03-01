"use client";

import { useEffect, useState, useCallback } from "react";
import { api, type Status, type SettingsResponse, type ApiToken, type ApiTokenCreateResult } from "@/lib/api";
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
  UserCog,
  LogOut,
  Key,
  Plus,
  Copy,
  Trash2,
  Lock,
  Globe,
  Bell,
  Timer,
  Activity,
  Boxes,
  Clock,
  Network,
  Search,
} from "lucide-react";
import Link from "next/link";
import { useAuth } from "@/components/auth-provider";

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

// --- Env-locked badge ---

function EnvLockedBadge() {
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
  label, settingKey, value, source, secret, localEdits, setLocalEdits, onReset, tooltip, envLocked,
}: {
  label: string; settingKey: string; value: string; source: "default" | "env" | "db";
  secret?: boolean; localEdits: Record<string, string>; setLocalEdits: (e: Record<string, string>) => void;
  onReset: (key: string) => void; tooltip?: string; envLocked?: boolean;
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

function EditableNumber({
  label, settingKey, value, source, localEdits, setLocalEdits, onReset, min, tooltip, envLocked,
}: {
  label: string; settingKey: string; value: number; source: "default" | "env" | "db";
  localEdits: Record<string, string>; setLocalEdits: (e: Record<string, string>) => void;
  onReset: (key: string) => void; min?: number; tooltip?: string; envLocked?: boolean;
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
      />
    </div>
  );
}

function EditableToggle({
  label, settingKey, value, source, localEdits, setLocalEdits, onReset, tooltip, envLocked,
}: {
  label: string; settingKey: string; value: boolean; source: "default" | "env" | "db";
  localEdits: Record<string, string>; setLocalEdits: (e: Record<string, string>) => void;
  onReset: (key: string) => void; tooltip?: string; envLocked?: boolean;
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
      />
    </div>
  );
}

function EditableSelect({
  label, settingKey, value, source, options, localEdits, setLocalEdits, onReset, tooltip, envLocked,
}: {
  label: string; settingKey: string; value: string; source: "default" | "env" | "db";
  options: string[]; localEdits: Record<string, string>; setLocalEdits: (e: Record<string, string>) => void;
  onReset: (key: string) => void; tooltip?: string; envLocked?: boolean;
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

// --- Personal Access Tokens (ca-162) ---

function PATSection() {
  const { user, authEnabled } = useAuth();
  const [tokens, setTokens] = useState<ApiToken[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [newTokenName, setNewTokenName] = useState("");
  const [newTokenDays, setNewTokenDays] = useState("");
  const [rawToken, setRawToken] = useState<ApiTokenCreateResult | null>(null);
  const [copied, setCopied] = useState(false);

  const loadTokens = useCallback(() => {
    setLoading(true);
    api.authTokens()
      .then(setTokens)
      .catch(() => setTokens([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (authEnabled && user) loadTokens();
  }, [authEnabled, user, loadTokens]);

  if (!authEnabled || !user) return null;

  const handleCreate = async () => {
    if (!newTokenName.trim()) return;
    setCreating(true);
    try {
      const days = newTokenDays ? parseInt(newTokenDays, 10) : undefined;
      const result = await api.authTokenCreate({
        name: newTokenName.trim(),
        expires_in_days: days,
      });
      setRawToken(result);
      setNewTokenName("");
      setNewTokenDays("");
      loadTokens();
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to create token");
    } finally {
      setCreating(false);
    }
  };

  const handleRevoke = async (tokenId: number) => {
    try {
      await api.authTokenRevoke(tokenId);
      toast.success("Token revoked");
      loadTokens();
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to revoke token");
    }
  };

  const handleCopy = async (text: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Card className="mb-4">
      <CardHeader className="p-4 pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Key className="h-4 w-4" />
          Personal Access Tokens
        </CardTitle>
      </CardHeader>
      <CardContent className="p-4 pt-0 space-y-3">
        <p className="text-xs text-muted-foreground">
          Use tokens to authenticate API and MCP clients. Tokens are shown once at creation.
        </p>

        {/* New token revealed */}
        {rawToken && (
          <div className="rounded-md border border-green-500/30 bg-green-500/10 p-3 space-y-2">
            <p className="text-xs font-medium text-green-300">
              Token created — copy it now, it won&apos;t be shown again.
            </p>
            <div className="flex items-center gap-2">
              <code className="flex-1 rounded bg-background px-2 py-1 text-xs font-mono break-all select-all">
                {rawToken.raw_token}
              </code>
              <Button
                variant="ghost"
                size="xs"
                onClick={() => handleCopy(rawToken.raw_token)}
              >
                <Copy className="h-3 w-3 mr-1" />
                {copied ? "Copied" : "Copy"}
              </Button>
            </div>
            <Button
              variant="ghost"
              size="xs"
              className="text-xs"
              onClick={() => setRawToken(null)}
            >
              Dismiss
            </Button>
          </div>
        )}

        {/* Create form */}
        <div className="flex items-end gap-2">
          <div className="flex-1">
            <Input
              placeholder="Token name (e.g. claude-code)"
              value={newTokenName}
              onChange={(e) => setNewTokenName(e.target.value)}
              className="h-7 text-xs"
              onKeyDown={(e) => e.key === "Enter" && handleCreate()}
            />
          </div>
          <div className="w-28">
            <Input
              type="number"
              placeholder="Days (empty=never)"
              value={newTokenDays}
              onChange={(e) => setNewTokenDays(e.target.value)}
              className="h-7 text-xs"
              min={1}
            />
          </div>
          <Button size="xs" onClick={handleCreate} disabled={creating || !newTokenName.trim()}>
            <Plus className="h-3 w-3 mr-1" />
            Create
          </Button>
        </div>

        {/* Token list */}
        {loading ? (
          <p className="text-xs text-muted-foreground">Loading...</p>
        ) : tokens.length === 0 ? (
          <p className="text-xs text-muted-foreground">No tokens yet.</p>
        ) : (
          <div className="divide-y divide-border">
            {tokens.map((t) => (
              <div key={t.id} className="flex items-center justify-between py-2 text-xs">
                <div className="flex items-center gap-3">
                  <span className="font-medium">{t.name}</span>
                  <code className="text-muted-foreground font-mono">{t.token_prefix}...</code>
                  {t.last_used_at && (
                    <span className="text-muted-foreground">
                      used {new Date(t.last_used_at).toLocaleDateString()}
                    </span>
                  )}
                  {t.expires_at && (
                    <span className={cn(
                      "text-muted-foreground",
                      new Date(t.expires_at) < new Date() && "text-red-400",
                    )}>
                      {new Date(t.expires_at) < new Date()
                        ? "expired"
                        : `expires ${new Date(t.expires_at).toLocaleDateString()}`}
                    </span>
                  )}
                </div>
                <Button
                  variant="ghost"
                  size="xs"
                  className="text-muted-foreground hover:text-destructive"
                  onClick={() => handleRevoke(t.id)}
                >
                  <Trash2 className="h-3 w-3" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// --- Auth user card (ca-124) ---

function AuthUserCard() {
  const { user, authEnabled, logout } = useAuth();
  if (!authEnabled || !user) return null;
  return (
    <Card className="mb-4">
      <CardContent className="flex items-center justify-between py-3">
        <div className="flex items-center gap-3 text-sm">
          <UserCog className="h-4 w-4 text-muted-foreground" />
          <span>Signed in as <strong>{user.username}</strong></span>
          <Badge variant={user.role === "admin" ? "destructive" : "secondary"}>
            {user.role}
          </Badge>
        </div>
        <div className="flex items-center gap-2">
          {user.role === "admin" && (
            <Link href="/admin/users">
              <Button variant="outline" size="sm">Manage Users</Button>
            </Link>
          )}
          <Button variant="ghost" size="sm" onClick={logout}>
            <LogOut className="mr-1 h-3 w-3" /> Sign Out
          </Button>
        </div>
      </CardContent>
    </Card>
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

  const [searchFilter, setSearchFilter] = useState("");

  const val = (key: string) => settings?.values[key];
  type SettingSource = "default" | "env" | "db";
  const src = (key: string): SettingSource =>
    (settings?.sources[key] as SettingSource) || "default";

  const isExperimental = (key: string) =>
    settings?.experimental?.includes(`capabilities.${key}`) ?? false;

  const isEnvLocked = (key: string) =>
    settings?.env_locked?.includes(key) ?? false;

  // Search filter: check if a section prefix or any of its keys match the filter
  const sectionVisible = (prefix: string, ...extraKeys: string[]) => {
    if (!searchFilter) return true;
    const q = searchFilter.toLowerCase();
    if (prefix.toLowerCase().includes(q)) return true;
    // Check if any key under this prefix matches
    if (settings?.values) {
      for (const key of Object.keys(settings.values)) {
        if (key.startsWith(prefix) && key.toLowerCase().includes(q)) return true;
      }
    }
    for (const k of extraKeys) {
      if (k.toLowerCase().includes(q)) return true;
    }
    return false;
  };

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
          {/* Search filter */}
          <div className="relative mb-4">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Filter settings..."
              value={searchFilter}
              onChange={(e) => setSearchFilter(e.target.value)}
              className="pl-9 h-9"
            />
          </div>

          {/* Restart banner */}
          {settings.pending_restart && (
            <div className="flex items-center gap-2 rounded-lg border border-yellow-500/30 bg-yellow-500/10 p-3 text-sm text-yellow-200 mb-4">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              <span>Settings have been changed. Restart the container to apply.</span>
            </div>
          )}

          {/* User info card (ca-124) */}
          <AuthUserCard />

          {/* Personal Access Tokens (ca-162) */}
          <PATSection />

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
            {sectionVisible("llm.", "enrichment_enabled") && <SectionCard
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
            </SectionCard>}

            {/* 2. Reranker */}
            {sectionVisible("reranker.") && <SectionCard
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
            </SectionCard>}

            {/* Router — full width, 3 tiers */}
            {sectionVisible("router.") && <SectionCard
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
            </SectionCard>}

            {/* 3. Auth */}
            {sectionVisible("auth.") && <SectionCard
              icon={<Shield className="h-4 w-4" />}
              title="Authentication"
              dirty={sectionDirty("auth.")}
              onSave={() => saveSection("auth.")}
              saving={saving === "auth."}
            >
              <EditableToggle label="Enabled" settingKey="auth.enabled" value={Boolean(val("auth.enabled"))} source={src("auth.enabled")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
              <EditableText label="API Key" settingKey="auth.api_key" value={String(val("auth.api_key") ?? "")} source={src("auth.api_key")} secret localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
              <EditableText label="Header" settingKey="auth.header_name" value={String(val("auth.header_name") ?? "X-API-Key")} source={src("auth.header_name")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
            </SectionCard>}

            {/* 3. Terminal */}
            {sectionVisible("terminal.") && <SectionCard
              icon={<Terminal className="h-4 w-4" />}
              title="Terminal"
              dirty={sectionDirty("terminal.")}
              onSave={() => saveSection("terminal.")}
              saving={saving === "terminal."}
            >
              <EditableSelect label="Backend" settingKey="terminal.backend" value={String(val("terminal.backend") ?? "disabled")} source={src("terminal.backend")} options={["native", "ttyd", "disabled"]} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
              <EditableNumber label="Max Sessions" settingKey="terminal.max_sessions" value={Number(val("terminal.max_sessions") ?? 5)} source={src("terminal.max_sessions")} min={1} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
              <EditableNumber label="Connect Timeout" settingKey="terminal.connect_timeout" value={Number(val("terminal.connect_timeout") ?? 30)} source={src("terminal.connect_timeout")} min={1} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} />
            </SectionCard>}

            {/* Neo4j */}
            {sectionVisible("neo4j.") && <SectionCard
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
            </SectionCard>}

            {/* 4. Analytics */}
            {sectionVisible("analytics.") && <SectionCard
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
            </SectionCard>}

            {/* 4. Ingestion */}
            {sectionVisible("ingest") && <SectionCard
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
            </SectionCard>}

            {/* Budget (token budgets) */}
            {sectionVisible("budget.") && <SectionCard
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
            </SectionCard>}

            {/* 5. LLM Capabilities — full width, stable/experimental split */}
            {sectionVisible("capabilities.") && <SectionCard
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
            </SectionCard>}

            {/* Audit Trail */}
            {sectionVisible("audit.") && (
            <SectionCard
              icon={<Eye className="h-4 w-4" />}
              title="Audit Trail"
              dirty={sectionDirty("audit.")}
              onSave={() => saveSection("audit.")}
              saving={saving === "audit."}
            >
              <EditableToggle label="Enabled" settingKey="audit.enabled" value={Boolean(val("audit.enabled"))} source={src("audit.enabled")} localEdits={localEdits} setLocalEdits={setLocalEdits} onReset={handleReset} envLocked={isEnvLocked("audit.enabled")} />
            </SectionCard>
            )}

            {/* Webhooks */}
            {sectionVisible("webhooks.") && (
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
            )}

            {/* Alerting */}
            {sectionVisible("alerting.") && (
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
            )}

            {/* Retention */}
            {sectionVisible("retention.") && (
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
            )}

            {/* OpenTelemetry */}
            {sectionVisible("otel.") && (
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
            )}

            {/* Workspace */}
            {sectionVisible("workspace.") && (
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
            )}

            {/* OIDC */}
            {sectionVisible("auth.oidc.") && (
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
            )}

            {/* Decay */}
            {sectionVisible("decay.") && (
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
            )}

            {/* Clustering */}
            {sectionVisible("clustering.") && (
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
            )}

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
