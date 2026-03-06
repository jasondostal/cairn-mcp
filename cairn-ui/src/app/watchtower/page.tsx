"use client";

import { useState, useEffect, useCallback } from "react";
import {
  api,
  type AlertRule,
  type AlertHistoryEntry,
  type AuditEntry,
  type Webhook,
  type WebhookDelivery,
  type RetentionPolicy,
  type RetentionStatus,
} from "@/lib/api";
import { PageLayout } from "@/components/page-layout";
import { ProjectPill } from "@/components/project-pill";
import { useSharedDays } from "@/lib/use-page-filters";
import { SkeletonList } from "@/components/skeleton-list";
import { ErrorState } from "@/components/error-state";
import { EmptyState } from "@/components/empty-state";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { TimeRangeFilter } from "@/components/time-range-filter";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { toast } from "sonner";
import {
  Bell,
  ScrollText,
  Webhook as WebhookIcon,
  Trash2,
  ChevronDown,
  ChevronRight,
  RefreshCw,
  Loader2,
  Send,
  Shield,
  Clock,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Pause,
  Plus,
  Power,
} from "lucide-react";

// ---------------------------------------------------------------------------
// OKLCH Palette — perceptually uniform, dark-mode optimized
// ---------------------------------------------------------------------------

const wt = {
  // Severity
  critical:   "oklch(0.645 0.246 16)",    // red
  warning:    "oklch(0.769 0.188 70)",    // gold
  info:       "oklch(0.55 0.2 264)",      // blue
  // Status
  ok:         "oklch(0.696 0.17 162)",    // teal
  fail:       "oklch(0.645 0.246 16)",    // red
  pending:    "oklch(0.769 0.188 70)",    // gold
  inactive:   "oklch(0.556 0 0)",         // gray
  // Accents per section
  alerts:     "oklch(0.705 0.213 47)",    // orange
  audit:      "oklch(0.55 0.2 264)",      // blue
  webhooks:   "oklch(0.488 0.243 264)",   // purple
  retention:  "oklch(0.696 0.17 162)",    // teal
  // Utility
  hold:       "oklch(0.645 0.246 16)",    // red
  count:      "oklch(0.705 0.213 47)",    // orange
} as const;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function timeAgo(iso: string | null): string {
  if (!iso) return "never";
  const d = new Date(iso);
  const s = Math.floor((Date.now() - d.getTime()) / 1000);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

const inputCls = "h-8 rounded-md border border-input bg-background px-2 text-xs";
const selectCls = `${inputCls} appearance-none`;

function severityBadge(s: string) {
  const color = s === "critical" ? wt.critical : s === "warning" ? wt.warning : wt.info;
  return (
    <span
      className="inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium"
      style={{ color, borderColor: `color-mix(in oklch, ${color} 40%, transparent)` }}
    >
      {s}
    </span>
  );
}

// ===========================================================================
// Alerts Tab
// ===========================================================================

function AlertsTab() {
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [active, setActive] = useState<AlertHistoryEntry[]>([]);
  const [history, setHistory] = useState<AlertHistoryEntry[]>([]);
  const [templates, setTemplates] = useState<Record<string, Record<string, unknown>>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState("");
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const [rulesRes, activeRes, historyRes, tplRes] = await Promise.all([
        api.alertRules({ limit: "100" }),
        api.alertActive({ hours: "24" }),
        api.alertHistory({ limit: "50", days: "7" }),
        api.alertTemplates(),
      ]);
      setRules(rulesRes.items ?? []);
      setActive(activeRes.active ?? []);
      setHistory(historyRes.items ?? []);
      setTemplates(tplRes.templates ?? {});
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load alerts");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const createFromTemplate = async () => {
    if (!selectedTemplate) return;
    const tpl = templates[selectedTemplate];
    if (!tpl) return;
    setCreating(true);
    try {
      await api.alertRuleCreate(tpl as Parameters<typeof api.alertRuleCreate>[0]);
      toast.success(`Alert rule "${tpl.name}" created`);
      setShowCreate(false);
      setSelectedTemplate("");
      load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to create rule");
    } finally {
      setCreating(false);
    }
  };

  const toggleRule = async (r: AlertRule) => {
    try {
      await api.alertRuleUpdate(r.id, { is_active: !r.is_active });
      toast.success(`Rule "${r.name}" ${r.is_active ? "paused" : "activated"}`);
      load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to update rule");
    }
  };

  const deleteRule = async (r: AlertRule) => {
    try {
      await api.alertRuleDelete(r.id);
      toast.success(`Rule "${r.name}" deleted`);
      load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to delete rule");
    }
  };

  if (loading) return <SkeletonList count={4} />;
  if (error) return <ErrorState message="Failed to load alerts" detail={error} />;

  return (
    <div className="space-y-4">
      {/* Active alerts banner */}
      {active.length > 0 && (
        <Card
          className="border bg-card"
          style={{
            borderColor: `color-mix(in oklch, ${wt.critical} 40%, transparent)`,
            background: `color-mix(in oklch, ${wt.critical} 5%, var(--background))`,
          }}
        >
          <CardHeader className="p-4 pb-2">
            <CardTitle className="flex items-center gap-2 text-sm" style={{ color: wt.critical }}>
              <AlertTriangle className="h-4 w-4" />
              {active.length} active alert{active.length !== 1 ? "s" : ""} (last 24h)
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-0 space-y-1">
            {active.map((a) => (
              <div key={a.id} className="flex items-center justify-between text-sm">
                <span className="flex items-center gap-2">
                  {severityBadge(a.severity)}
                  <span className="font-medium">{a.rule_name}</span>
                  <span className="text-muted-foreground truncate max-w-md">{a.message}</span>
                </span>
                <span className="text-xs text-muted-foreground shrink-0">{timeAgo(a.fired_at)}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Rules */}
      <Card>
        <CardHeader className="p-4 pb-2">
          <CardTitle className="flex items-center justify-between text-sm">
            <span className="flex items-center gap-2">
              <Bell className="h-4 w-4" style={{ color: wt.alerts }} />
              Alert Rules ({rules.length})
            </span>
            <div className="flex items-center gap-1">
              <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => setShowCreate(!showCreate)}>
                <Plus className="h-3.5 w-3.5 mr-1" /> New Rule
              </Button>
              <Button variant="ghost" size="sm" onClick={load} className="h-7 px-2">
                <RefreshCw className="h-3.5 w-3.5" />
              </Button>
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent className="p-4 pt-0">
          {/* Create from template */}
          {showCreate && (
            <div className="flex items-center gap-2 pb-3 mb-3 border-b border-border">
              <select
                value={selectedTemplate}
                onChange={(e) => setSelectedTemplate(e.target.value)}
                className={`${selectCls} flex-1`}
              >
                <option value="">Select a template...</option>
                {Object.entries(templates).map(([key, tpl]) => (
                  <option key={key} value={key}>{(tpl as Record<string, unknown>).name as string} — {key}</option>
                ))}
              </select>
              <Button size="sm" className="h-8 text-xs" onClick={createFromTemplate} disabled={!selectedTemplate || creating}>
                {creating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Create"}
              </Button>
            </div>
          )}

          {rules.length === 0 && !showCreate ? (
            <p className="text-sm text-muted-foreground py-4 text-center">No alert rules configured.</p>
          ) : (
            <div className="divide-y divide-border">
              {rules.map((r) => (
                <div key={r.id} className="flex items-center justify-between py-2 text-sm">
                  <div className="flex items-center gap-2">
                    {r.is_active ? (
                      <CheckCircle className="h-3.5 w-3.5 shrink-0" style={{ color: wt.ok }} />
                    ) : (
                      <Pause className="h-3.5 w-3.5 shrink-0" style={{ color: wt.inactive }} />
                    )}
                    <span className="font-medium">{r.name}</span>
                    {severityBadge(r.severity)}
                    <span className="text-xs text-muted-foreground">{r.condition_type}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground">fired {timeAgo(r.last_fired_at)}</span>
                    <Button variant="ghost" size="sm" className="h-6 w-6 p-0" onClick={() => toggleRule(r)} title={r.is_active ? "Pause" : "Activate"}>
                      <Power className="h-3 w-3" />
                    </Button>
                    <Button variant="ghost" size="sm" className="h-6 w-6 p-0" onClick={() => deleteRule(r)} title="Delete">
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Recent history */}
      <Card>
        <CardHeader className="p-4 pb-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <Clock className="h-4 w-4" style={{ color: wt.alerts }} />
            Alert History (7d)
          </CardTitle>
        </CardHeader>
        <CardContent className="p-4 pt-0">
          {history.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4 text-center">No alerts fired in the last 7 days.</p>
          ) : (
            <div className="divide-y divide-border">
              {history.map((h) => (
                <div key={h.id} className="flex items-center justify-between py-1.5 text-sm">
                  <span className="flex items-center gap-2">
                    {severityBadge(h.severity)}
                    <span className="font-medium">{h.rule_name}</span>
                    <span className="text-muted-foreground truncate max-w-sm">{h.message}</span>
                  </span>
                  <span className="text-xs text-muted-foreground shrink-0">{timeAgo(h.fired_at)}</span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ===========================================================================
// Audit Tab
// ===========================================================================

function AuditTab() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sharedDays, setSharedDays] = useSharedDays(7);
  const [filters, setFilters] = useState({ actor: "", action: "", resource_type: "" });
  const [expanded, setExpanded] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const opts: Record<string, string> = { limit: "100" };
      if (filters.actor) opts.actor = filters.actor;
      if (filters.action) opts.action = filters.action;
      if (filters.resource_type) opts.resource_type = filters.resource_type;
      opts.days = String(sharedDays);
      const res = await api.auditQuery(opts);
      setEntries(res.items ?? []);
      setTotal(res.total ?? 0);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load audit log");
    } finally {
      setLoading(false);
    }
  }, [filters, sharedDays]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        <input
          placeholder="Actor..."
          value={filters.actor}
          onChange={(e) => setFilters((f) => ({ ...f, actor: e.target.value }))}
          className="h-8 rounded-md border border-input bg-background px-2 text-xs w-28"
        />
        <input
          placeholder="Action..."
          value={filters.action}
          onChange={(e) => setFilters((f) => ({ ...f, action: e.target.value }))}
          className="h-8 rounded-md border border-input bg-background px-2 text-xs w-28"
        />
        <input
          placeholder="Resource type..."
          value={filters.resource_type}
          onChange={(e) => setFilters((f) => ({ ...f, resource_type: e.target.value }))}
          className="h-8 rounded-md border border-input bg-background px-2 text-xs w-32"
        />
        <TimeRangeFilter
          days={sharedDays}
          onChange={setSharedDays}
          presets={[
            { label: "1d", value: 1 },
            { label: "7d", value: 7 },
            { label: "30d", value: 30 },
            { label: "90d", value: 90 },
          ]}
        />
        <Button variant="ghost" size="sm" onClick={load} className="h-8 px-2">
          <RefreshCw className="h-3.5 w-3.5" />
        </Button>
        <span className="text-xs text-muted-foreground self-center ml-auto">{total} entries</span>
      </div>

      {loading && <SkeletonList count={8} />}
      {error && <ErrorState message="Failed to load audit log" detail={error} />}

      {!loading && !error && entries.length === 0 && (
        <EmptyState message="No audit entries" detail="Audit entries appear when operations are performed." />
      )}

      {!loading && !error && entries.length > 0 && (
        <div className="rounded-md border divide-y divide-border">
          {entries.map((e) => (
            <div key={e.id}>
              <button
                onClick={() => setExpanded(expanded === e.id ? null : e.id)}
                className="flex items-center gap-2 w-full px-3 py-1.5 text-sm hover:bg-accent/50 text-left"
              >
                {expanded === e.id ? (
                  <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                ) : (
                  <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                )}
                <span className="font-mono text-xs text-muted-foreground w-16 shrink-0">{e.actor}</span>
                <Badge variant="secondary" className="text-[10px]">{e.action}</Badge>
                <span className="text-muted-foreground">{e.resource_type}</span>
                {e.project && <ProjectPill name={e.project} />}
                <span className="text-xs text-muted-foreground ml-auto shrink-0">{timeAgo(e.created_at)}</span>
              </button>
              {expanded === e.id && (
                <div className="px-3 pb-2 pl-8 text-xs">
                  {e.trace_id && (
                    <div className="text-muted-foreground">
                      <span className="font-medium">trace:</span> {e.trace_id}
                    </div>
                  )}
                  {e.resource_id != null && (
                    <div className="text-muted-foreground">
                      <span className="font-medium">resource_id:</span> {e.resource_id}
                    </div>
                  )}
                  {e.detail && (
                    <pre className="mt-1 p-2 rounded bg-muted text-[11px] overflow-x-auto max-h-48">
                      {JSON.stringify(e.detail, null, 2)}
                    </pre>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ===========================================================================
// Webhooks Tab
// ===========================================================================

const WEBHOOK_EVENT_TYPES = [
  "memory.*", "work_item.*", "session_start", "session_end",
  "thinking.*", "task.*", "project.*",
];

function WebhooksTab() {
  const [hooks, setHooks] = useState<Webhook[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [deliveries, setDeliveries] = useState<Record<number, WebhookDelivery[]>>({});
  const [testing, setTesting] = useState<number | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [newHook, setNewHook] = useState({ name: "", url: "", event_types: ["*"] as string[] });
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const res = await api.webhooks({ active_only: "false", limit: "100" });
      setHooks(res.items ?? []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load webhooks");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const createWebhook = async () => {
    if (!newHook.name || !newHook.url) return;
    setCreating(true);
    try {
      await api.webhookCreate(newHook);
      toast.success(`Webhook "${newHook.name}" created`);
      setShowCreate(false);
      setNewHook({ name: "", url: "", event_types: ["*"] });
      load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to create webhook");
    } finally {
      setCreating(false);
    }
  };

  const toggleWebhook = async (h: Webhook) => {
    try {
      await api.webhookUpdate(h.id, { is_active: !h.is_active });
      toast.success(`Webhook "${h.name}" ${h.is_active ? "paused" : "activated"}`);
      load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to update webhook");
    }
  };

  const deleteWebhook = async (h: Webhook) => {
    try {
      await api.webhookDelete(h.id);
      toast.success(`Webhook "${h.name}" deleted`);
      load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to delete webhook");
    }
  };

  const toggleExpand = async (id: number) => {
    if (expanded === id) {
      setExpanded(null);
      return;
    }
    setExpanded(id);
    if (!deliveries[id]) {
      try {
        const res = await api.webhookDeliveries(id, { limit: "20" });
        setDeliveries((d) => ({ ...d, [id]: res.items ?? [] }));
      } catch {
        // ignore
      }
    }
  };

  const testWebhook = async (id: number) => {
    setTesting(id);
    try {
      const res = await api.webhookTest(id);
      if (res.status === "success") {
        toast.success(`Test delivery succeeded (HTTP ${res.http_status})`);
      } else {
        toast.error(`Test delivery failed: ${res.error || `HTTP ${res.http_status}`}`);
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Test delivery failed");
    } finally {
      setTesting(null);
    }
  };

  if (loading) return <SkeletonList count={4} />;
  if (error) return <ErrorState message="Failed to load webhooks" detail={error} />;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm text-muted-foreground">{hooks.length} webhook{hooks.length !== 1 ? "s" : ""}</span>
        <div className="flex items-center gap-1">
          <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => setShowCreate(!showCreate)}>
            <Plus className="h-3.5 w-3.5 mr-1" /> New Webhook
          </Button>
          <Button variant="ghost" size="sm" onClick={load} className="h-7 px-2">
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* Create form */}
      {showCreate && (
        <Card>
          <CardContent className="p-4 space-y-3">
            <div className="flex gap-2">
              <input placeholder="Name" value={newHook.name} onChange={(e) => setNewHook((h) => ({ ...h, name: e.target.value }))} className={`${inputCls} flex-1`} />
              <input placeholder="https://..." value={newHook.url} onChange={(e) => setNewHook((h) => ({ ...h, url: e.target.value }))} className={`${inputCls} flex-[2]`} />
            </div>
            <div className="flex flex-wrap gap-1.5">
              {WEBHOOK_EVENT_TYPES.map((t) => {
                const selected = newHook.event_types.includes(t);
                return (
                  <button
                    key={t}
                    onClick={() => setNewHook((h) => ({
                      ...h,
                      event_types: selected ? h.event_types.filter((e) => e !== t) : [...h.event_types.filter((e) => e !== "*"), t],
                    }))}
                    className={`rounded-full border px-2 py-0.5 text-[10px] transition-colors ${selected ? "border-primary text-foreground" : "border-input text-muted-foreground hover:text-foreground"}`}
                  >
                    {t}
                  </button>
                );
              })}
              <button
                onClick={() => setNewHook((h) => ({ ...h, event_types: ["*"] }))}
                className={`rounded-full border px-2 py-0.5 text-[10px] transition-colors ${newHook.event_types.includes("*") ? "border-primary text-foreground" : "border-input text-muted-foreground hover:text-foreground"}`}
              >
                * (all)
              </button>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => setShowCreate(false)}>Cancel</Button>
              <Button size="sm" className="h-7 text-xs" onClick={createWebhook} disabled={!newHook.name || !newHook.url || creating}>
                {creating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Create"}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {hooks.length === 0 && !showCreate && (
        <EmptyState message="No webhooks configured" detail="Click 'New Webhook' to create one." />
      )}

      {hooks.map((h) => (
        <Card key={h.id}>
          <CardHeader className="p-4 pb-2">
            <CardTitle className="flex items-center justify-between text-sm">
              <span className="flex items-center gap-2">
                {h.is_active ? (
                  <CheckCircle className="h-3.5 w-3.5" style={{ color: wt.ok }} />
                ) : (
                  <XCircle className="h-3.5 w-3.5" style={{ color: wt.inactive }} />
                )}
                <span className="font-medium">{h.name}</span>
                <span className="text-xs text-muted-foreground font-normal truncate max-w-xs">{h.url}</span>
              </span>
              <div className="flex items-center gap-1">
                <Button variant="ghost" size="sm" className="h-7 px-2" onClick={() => toggleWebhook(h)} title={h.is_active ? "Pause" : "Activate"}>
                  <Power className="h-3.5 w-3.5" />
                </Button>
                <Button variant="ghost" size="sm" className="h-7 px-2" onClick={() => testWebhook(h.id)} disabled={testing === h.id}>
                  {testing === h.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
                </Button>
                <Button variant="ghost" size="sm" className="h-7 px-2" onClick={() => deleteWebhook(h)} title="Delete">
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
                <Button variant="ghost" size="sm" className="h-7 px-2" onClick={() => toggleExpand(h.id)}>
                  {expanded === h.id ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                </Button>
              </div>
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-0">
            <div className="flex flex-wrap gap-1">
              {h.event_types.map((t) => (
                <Badge key={t} variant="secondary" className="text-[10px]">{t}</Badge>
              ))}
            </div>

            {expanded === h.id && (
              <div className="mt-3 border-t pt-3">
                <p className="text-xs font-medium text-muted-foreground mb-2">Recent Deliveries</p>
                {!deliveries[h.id] ? (
                  <p className="text-xs text-muted-foreground">Loading...</p>
                ) : deliveries[h.id].length === 0 ? (
                  <p className="text-xs text-muted-foreground">No deliveries yet.</p>
                ) : (
                  <div className="divide-y divide-border text-xs">
                    {deliveries[h.id].map((d) => (
                      <div key={d.id} className="flex items-center justify-between py-1">
                        <span className="flex items-center gap-2">
                          {d.status === "succeeded" ? (
                            <CheckCircle className="h-3 w-3" style={{ color: wt.ok }} />
                          ) : d.status === "failed" ? (
                            <XCircle className="h-3 w-3" style={{ color: wt.fail }} />
                          ) : (
                            <Clock className="h-3 w-3" style={{ color: wt.pending }} />
                          )}
                          <span>{d.event_type}</span>
                          {d.http_status && (
                            <span className="text-muted-foreground">HTTP {d.http_status}</span>
                          )}
                        </span>
                        <span className="text-muted-foreground">{timeAgo(d.created_at)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

// ===========================================================================
// Retention Tab
// ===========================================================================

const RESOURCE_TYPES = [
  "events", "usage_events", "metric_rollups", "webhook_deliveries",
  "alert_history", "audit_log", "event_dispatches",
];

const DEFAULT_TTL: Record<string, number> = {
  events: 90, usage_events: 60, metric_rollups: 180,
  webhook_deliveries: 30, alert_history: 90, audit_log: 365, event_dispatches: 14,
};

function RetentionTab() {
  const [policies, setPolicies] = useState<RetentionPolicy[]>([]);
  const [status, setStatus] = useState<RetentionStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [preview, setPreview] = useState<Array<{ policy_id: number; resource_type: string; would_delete: number; reason?: string }> | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [newPolicy, setNewPolicy] = useState({ resource_type: "events", ttl_days: 90, legal_hold: false });
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const [policiesRes, statusRes] = await Promise.all([
        api.retentionPolicies({ limit: "100" }),
        api.retentionStatus(),
      ]);
      setPolicies(policiesRes.items ?? []);
      setStatus(statusRes);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load retention");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const createPolicy = async () => {
    setCreating(true);
    try {
      await api.retentionPolicyCreate(newPolicy);
      toast.success(`Retention policy for ${newPolicy.resource_type} created`);
      setShowCreate(false);
      setNewPolicy({ resource_type: "events", ttl_days: 90, legal_hold: false });
      load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to create policy");
    } finally {
      setCreating(false);
    }
  };

  const togglePolicy = async (p: RetentionPolicy) => {
    try {
      await api.retentionPolicyUpdate(p.id, { is_active: !p.is_active });
      toast.success(`Policy for ${p.resource_type} ${p.is_active ? "paused" : "activated"}`);
      load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to update policy");
    }
  };

  const deletePolicy = async (p: RetentionPolicy) => {
    try {
      await api.retentionPolicyDelete(p.id);
      toast.success(`Policy for ${p.resource_type} deleted`);
      load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to delete policy");
    }
  };

  const runPreview = async () => {
    setPreviewing(true);
    try {
      const res = await api.retentionPreview();
      setPreview(res.results);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Preview failed");
    } finally {
      setPreviewing(false);
    }
  };

  if (loading) return <SkeletonList count={3} />;
  if (error) return <ErrorState message="Failed to load retention" detail={error} />;

  return (
    <div className="space-y-4">
      {/* Status card */}
      {status && (
        <Card>
          <CardHeader className="p-4 pb-2">
            <CardTitle className="flex items-center gap-2 text-sm">
              <Shield className="h-4 w-4" style={{ color: wt.retention }} />
              Retention Scanner
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-0">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <div>
                <p className="text-xs text-muted-foreground">Policies</p>
                <p className="text-lg font-semibold">{status.active_policies}<span className="text-muted-foreground text-sm">/{status.total_policies}</span></p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Legal Holds</p>
                <p className="text-lg font-semibold">{status.held_policies}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Total Deleted</p>
                <p className="text-lg font-semibold">{status.total_deleted.toLocaleString()}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Last Scan</p>
                <p className="text-sm font-medium">{timeAgo(status.last_run_at)}</p>
              </div>
            </div>
            <div className="mt-3 flex items-center gap-3 text-xs text-muted-foreground">
              <span>Scan interval: {status.scan_interval_hours}h</span>
              {status.dry_run && (
                <span
                  className="inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium"
                  style={{ color: wt.pending, borderColor: `color-mix(in oklch, ${wt.pending} 40%, transparent)` }}
                >
                  Dry Run
                </span>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Policies */}
      <Card>
        <CardHeader className="p-4 pb-2">
          <CardTitle className="flex items-center justify-between text-sm">
            <span className="flex items-center gap-2">
              <Trash2 className="h-4 w-4" style={{ color: wt.retention }} />
              Retention Policies ({policies.length})
            </span>
            <div className="flex items-center gap-1">
              <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => setShowCreate(!showCreate)}>
                <Plus className="h-3.5 w-3.5 mr-1" /> New Policy
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="h-7 text-xs"
                onClick={runPreview}
                disabled={previewing}
              >
                {previewing && <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />}
                Dry Run
              </Button>
              <Button variant="ghost" size="sm" onClick={load} className="h-7 px-2">
                <RefreshCw className="h-3.5 w-3.5" />
              </Button>
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent className="p-4 pt-0">
          {/* Create form */}
          {showCreate && (
            <div className="flex items-center gap-2 pb-3 mb-3 border-b border-border">
              <select
                value={newPolicy.resource_type}
                onChange={(e) => setNewPolicy((p) => ({
                  ...p,
                  resource_type: e.target.value,
                  ttl_days: DEFAULT_TTL[e.target.value] ?? 90,
                }))}
                className={`${selectCls} w-44`}
              >
                {RESOURCE_TYPES.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
              <div className="flex items-center gap-1">
                <input
                  type="number"
                  min={1}
                  value={newPolicy.ttl_days}
                  onChange={(e) => setNewPolicy((p) => ({ ...p, ttl_days: parseInt(e.target.value) || 1 }))}
                  className={`${inputCls} w-20 text-center`}
                />
                <span className="text-xs text-muted-foreground">days</span>
              </div>
              <label className="flex items-center gap-1 text-xs text-muted-foreground cursor-pointer">
                <input
                  type="checkbox"
                  checked={newPolicy.legal_hold}
                  onChange={(e) => setNewPolicy((p) => ({ ...p, legal_hold: e.target.checked }))}
                  className="rounded"
                />
                Legal hold
              </label>
              <Button size="sm" className="h-8 text-xs ml-auto" onClick={createPolicy} disabled={creating}>
                {creating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Create"}
              </Button>
            </div>
          )}

          {policies.length === 0 && !showCreate ? (
            <p className="text-sm text-muted-foreground py-4 text-center">No retention policies configured.</p>
          ) : (
            <div className="divide-y divide-border">
              {policies.map((p) => {
                const prev = preview?.find((pr) => pr.policy_id === p.id);
                return (
                  <div key={p.id} className="flex items-center justify-between py-2 text-sm">
                    <div className="flex items-center gap-2">
                      {p.is_active ? (
                        <CheckCircle className="h-3.5 w-3.5 shrink-0" style={{ color: wt.ok }} />
                      ) : (
                        <Pause className="h-3.5 w-3.5 shrink-0" style={{ color: wt.inactive }} />
                      )}
                      <Badge variant="secondary">{p.resource_type}</Badge>
                      <span className="text-muted-foreground">{p.ttl_days}d TTL</span>
                      {p.project_id && <span className="text-xs text-muted-foreground/60">({p.project_id})</span>}
                      {p.legal_hold && (
                        <span
                          className="inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium"
                          style={{ color: wt.hold, borderColor: `color-mix(in oklch, ${wt.hold} 40%, transparent)` }}
                        >
                          HOLD
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      {prev && (
                        <span style={prev.would_delete > 0 ? { color: wt.count, fontWeight: 500 } : undefined}>
                          {prev.reason === "legal_hold" ? "held" : `${prev.would_delete.toLocaleString()} to delete`}
                        </span>
                      )}
                      <span>deleted: {p.last_deleted.toLocaleString()}</span>
                      <span>ran {timeAgo(p.last_run_at)}</span>
                      <Button variant="ghost" size="sm" className="h-6 w-6 p-0" onClick={() => togglePolicy(p)} title={p.is_active ? "Pause" : "Activate"}>
                        <Power className="h-3 w-3" />
                      </Button>
                      <Button variant="ghost" size="sm" className="h-6 w-6 p-0" onClick={() => deletePolicy(p)} title="Delete">
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ===========================================================================
// Main Page
// ===========================================================================

export default function WatchtowerPage() {
  const [tab, setTab] = useState("alerts");

  return (
    <PageLayout title="Watchtower" iconColor={wt.alerts}>
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList variant="line">
          <TabsTrigger value="alerts" style={tab === "alerts" ? { color: wt.alerts } : undefined}>
            <Bell className="h-3.5 w-3.5 mr-1" />
            Alerts
          </TabsTrigger>
          <TabsTrigger value="audit" style={tab === "audit" ? { color: wt.audit } : undefined}>
            <ScrollText className="h-3.5 w-3.5 mr-1" />
            Audit
          </TabsTrigger>
          <TabsTrigger value="webhooks" style={tab === "webhooks" ? { color: wt.webhooks } : undefined}>
            <WebhookIcon className="h-3.5 w-3.5 mr-1" />
            Webhooks
          </TabsTrigger>
          <TabsTrigger value="retention" style={tab === "retention" ? { color: wt.retention } : undefined}>
            <Trash2 className="h-3.5 w-3.5 mr-1" />
            Retention
          </TabsTrigger>
        </TabsList>

        <TabsContent value="alerts" className="mt-4">
          <AlertsTab />
        </TabsContent>

        <TabsContent value="audit" className="mt-4">
          <AuditTab />
        </TabsContent>

        <TabsContent value="webhooks" className="mt-4">
          <WebhooksTab />
        </TabsContent>

        <TabsContent value="retention" className="mt-4">
          <RetentionTab />
        </TabsContent>
      </Tabs>
    </PageLayout>
  );
}
