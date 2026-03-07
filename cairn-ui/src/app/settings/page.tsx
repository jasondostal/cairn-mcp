"use client";

import { useEffect, useState, useCallback } from "react";
import { api, type Status, type SettingsResponse } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { ErrorState } from "@/components/error-state";
import { SkeletonList } from "@/components/skeleton-list";
import { PageLayout } from "@/components/page-layout";
import { toast } from "sonner";
import { AlertTriangle, Search } from "lucide-react";
import { AuthUserCard } from "@/components/settings/auth-user-card";
import { PATSection } from "@/components/settings/pat-section";
import {
  SystemOverviewSection,
  EmbeddingSection,
  LLMSection,
  RerankerSection,
  RouterSection,
  AuthSection,
  TerminalSection,
  Neo4jSection,
  AnalyticsSection,
  IngestionSection,
  BudgetSection,
  CapabilitiesSection,
  AuditSection,
  WebhooksSection,
  AlertingSection,
  RetentionSection,
  OtelSection,
  WorkspaceSection,
  OIDCSection,
  DecaySection,
  ClusteringSection,
  DatabaseSection,
  MemoryTypesSection,
  type SettingsSectionProps,
} from "@/components/settings/settings-sections";

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

  // Build shared props for all section components
  const sectionProps: SettingsSectionProps | null =
    status && settings
      ? {
          status,
          settings,
          localEdits,
          setLocalEdits,
          saving,
          sectionVisible,
          sectionDirty,
          dirtyKeys,
          saveSection,
          saveKeys,
          handleReset,
          val,
          src,
          isEnvLocked,
          isExperimental,
        }
      : null;

  return (
    <PageLayout title="Settings">
      {loading && <SkeletonList count={4} height="h-32" />}
      {error && <ErrorState message="Failed to load settings" detail={error} />}

      {!loading && !error && sectionProps && (
        <>
          {/* Search filter */}
          <div className="relative mb-4">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              aria-label="Filter settings"
              placeholder="Filter settings..."
              value={searchFilter}
              onChange={(e) => setSearchFilter(e.target.value)}
              className="pl-9 h-9"
            />
          </div>

          {/* Restart banner */}
          {settings!.pending_restart && (
            <div className="flex items-center gap-2 rounded-lg border border-yellow-500/30 bg-yellow-500/10 p-3 text-sm text-yellow-200 mb-4">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              <span>Settings have been changed. Restart the container to apply.</span>
            </div>
          )}

          {/* User info card */}
          <AuthUserCard />

          {/* Personal Access Tokens */}
          <PATSection />

          <div className="grid gap-4 md:grid-cols-2">
            <SystemOverviewSection {...sectionProps} />
            <EmbeddingSection {...sectionProps} />
            <LLMSection {...sectionProps} />
            <RerankerSection {...sectionProps} />
            <RouterSection {...sectionProps} />
            <AuthSection {...sectionProps} />
            <TerminalSection {...sectionProps} />
            <Neo4jSection {...sectionProps} />
            <AnalyticsSection {...sectionProps} />
            <IngestionSection {...sectionProps} />
            <BudgetSection {...sectionProps} />
            <CapabilitiesSection {...sectionProps} />
            <AuditSection {...sectionProps} />
            <WebhooksSection {...sectionProps} />
            <AlertingSection {...sectionProps} />
            <RetentionSection {...sectionProps} />
            <OtelSection {...sectionProps} />
            <WorkspaceSection {...sectionProps} />
            <OIDCSection {...sectionProps} />
            <DecaySection {...sectionProps} />
            <ClusteringSection {...sectionProps} />
            <DatabaseSection {...sectionProps} />
            <MemoryTypesSection {...sectionProps} />
          </div>
        </>
      )}
    </PageLayout>
  );
}
