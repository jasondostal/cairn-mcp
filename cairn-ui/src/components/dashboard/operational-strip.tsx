"use client";

import { Card, CardContent } from "@/components/ui/card";
import { useFetch } from "@/lib/use-fetch";
import { api } from "@/lib/api";
import type { WorkItem, WorkItemStatus, Paginated } from "@/lib/api";
import {
  Kanban,
  AlertTriangle,
  Radio,
  Workflow,
} from "lucide-react";

interface SessionsResponse {
  count: number;
  items: Array<{ is_active: boolean }>;
}

interface GatedResponse {
  total: number;
}

const STATUS_ORDER: WorkItemStatus[] = ["open", "ready", "in_progress", "blocked"];

const STATUS_COLORS: Record<WorkItemStatus, string> = {
  open: "oklch(0.556 0 0)",
  ready: "oklch(0.488 0.243 264)",
  in_progress: "oklch(0.769 0.188 70)",
  blocked: "oklch(0.645 0.246 16)",
  done: "oklch(0.696 0.17 162)",
  cancelled: "oklch(0.556 0 0)",
};

const STATUS_LABELS: Record<string, string> = {
  open: "Open",
  ready: "Ready",
  in_progress: "WIP",
  blocked: "Blocked",
};

function StatusBar({ counts, total }: { counts: Record<string, number>; total: number }) {
  if (total === 0) return <div className="h-1.5 rounded-full bg-muted" />;

  return (
    <div className="flex h-1.5 rounded-full overflow-hidden bg-muted">
      {STATUS_ORDER.map((s) => {
        const c = counts[s] ?? 0;
        if (c === 0) return null;
        return (
          <div
            key={s}
            className="h-full transition-all"
            style={{
              width: `${(c / total) * 100}%`,
              backgroundColor: STATUS_COLORS[s],
            }}
          />
        );
      })}
    </div>
  );
}

function Stat({
  value,
  label,
  icon: Icon,
  accent,
}: {
  value: number | string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  accent?: boolean;
}) {
  return (
    <div className="flex items-center gap-2">
      <div className="rounded-md bg-muted p-1.5">
        <Icon className="h-3.5 w-3.5 text-muted-foreground" />
      </div>
      <div>
        <p className={`text-lg font-semibold tabular-nums leading-tight ${accent ? "text-amber-500" : ""}`}>
          {value}
        </p>
        <p className="text-[10px] text-muted-foreground leading-tight">{label}</p>
      </div>
    </div>
  );
}

export function OperationalStrip() {
  const { data: workItems } = useFetch<Paginated<WorkItem>>(
    () => api.workItems({ limit: "100" }),
    [],
  );

  const { data: gated } = useFetch<GatedResponse>(
    () => api.workItemsGated({ limit: "1" }),
    [],
  );

  const { data: sessions } = useFetch<SessionsResponse>(
    () => fetch("/api/sessions?limit=100").then((r) => r.json()),
    [],
  );

  // Aggregate work items by status (exclude done/cancelled)
  const statusCounts: Record<string, number> = {};
  let activeTotal = 0;
  if (workItems?.items) {
    for (const item of workItems.items) {
      if (item.status === "done" || item.status === "cancelled") continue;
      statusCounts[item.status] = (statusCounts[item.status] ?? 0) + 1;
      activeTotal++;
    }
  }

  const gatedCount = gated?.total ?? 0;
  const activeSessions = sessions?.items?.filter((s) => s.is_active).length ?? 0;

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center gap-6 flex-wrap">
          {/* Work items summary */}
          <div className="flex-1 min-w-[200px]">
            <div className="flex items-center gap-1.5 mb-2">
              <Kanban className="h-3.5 w-3.5 text-muted-foreground" />
              <span className="text-xs font-medium text-muted-foreground">Work Items</span>
              <span className="text-xs tabular-nums text-muted-foreground/60 ml-auto">{activeTotal} active</span>
            </div>
            <StatusBar counts={statusCounts} total={activeTotal} />
            <div className="flex gap-3 mt-1.5">
              {STATUS_ORDER.map((s) => {
                const c = statusCounts[s] ?? 0;
                return (
                  <div key={s} className="flex items-center gap-1">
                    <span
                      className="inline-block h-1.5 w-1.5 rounded-full"
                      style={{ backgroundColor: STATUS_COLORS[s] }}
                    />
                    <span className="text-[10px] tabular-nums text-muted-foreground">
                      {c} {STATUS_LABELS[s]}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Divider */}
          <div className="h-10 w-px bg-border hidden sm:block" />

          {/* Key stats */}
          <div className="flex items-center gap-5">
            <Stat
              value={gatedCount}
              label="Gated"
              icon={AlertTriangle}
              accent={gatedCount > 0}
            />
            <Stat
              value={activeSessions}
              label="Sessions"
              icon={Radio}
            />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
