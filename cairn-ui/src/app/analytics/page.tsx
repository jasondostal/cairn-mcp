"use client";

import { useState } from "react";
import {
  api,
  type AnalyticsOperation,
} from "@/lib/api";
import { useFetch } from "@/lib/use-fetch";
import { Button } from "@/components/ui/button";
import { PageLayout } from "@/components/page-layout";
import { SkeletonList } from "@/components/skeleton-list";
import { ErrorState } from "@/components/error-state";
import { EmptyState } from "@/components/empty-state";
import { Badge } from "@/components/ui/badge";
import Link from "next/link";
import { ChevronRight, AlertTriangle } from "lucide-react";

const DAY_PRESETS = [
  { label: "7d", value: 7 },
  { label: "30d", value: 30 },
  { label: "90d", value: 90 },
] as const;

function OpRow({ op }: { op: AnalyticsOperation }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div>
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-3 px-3 py-1.5 text-xs w-full text-left hover:bg-accent/50 transition-colors"
      >
        <ChevronRight
          className={`h-3 w-3 shrink-0 text-muted-foreground transition-transform ${expanded ? "rotate-90" : ""}`}
        />
        <Badge
          variant={op.success ? "secondary" : "destructive"}
          className="text-[10px] shrink-0"
        >
          {op.success ? "OK" : "ERR"}
        </Badge>
        <span className="font-mono font-medium truncate max-w-[200px]">
          {op.operation}
        </span>
        {!op.success && op.error_message && (
          <span className="text-destructive/70 truncate max-w-[200px] hidden md:inline">
            {op.error_message.split("\n")[0]}
          </span>
        )}
        {op.project && (
          <span className="text-muted-foreground truncate max-w-[120px] hidden sm:inline">
            {op.project}
          </span>
        )}
        <span className="tabular-nums text-muted-foreground ml-auto shrink-0">
          {op.latency_ms.toFixed(0)}ms
        </span>
        {(op.tokens_in > 0 || op.tokens_out > 0) && (
          <span className="tabular-nums text-muted-foreground shrink-0 hidden sm:inline">
            {op.tokens_in}/{op.tokens_out}t
          </span>
        )}
        <span className="text-muted-foreground shrink-0">
          {new Date(op.timestamp).toLocaleTimeString()}
        </span>
      </button>

      {expanded && (
        <div className="px-3 pb-3 pt-1 ml-6 space-y-2 text-xs border-l-2 border-border ml-[22px]">
          {/* Detail grid */}
          <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-muted-foreground">
            <span className="font-medium">Operation</span>
            <span className="font-mono">{op.operation}</span>

            {op.model && (
              <>
                <span className="font-medium">Model</span>
                <span className="font-mono">{op.model}</span>
              </>
            )}

            <span className="font-medium">Latency</span>
            <span className="tabular-nums">{op.latency_ms.toFixed(1)}ms</span>

            {(op.tokens_in > 0 || op.tokens_out > 0) && (
              <>
                <span className="font-medium">Tokens</span>
                <span className="tabular-nums">
                  {op.tokens_in.toLocaleString()} in / {op.tokens_out.toLocaleString()} out
                </span>
              </>
            )}

            {op.project && (
              <>
                <span className="font-medium">Project</span>
                <Link
                  href={`/projects/${encodeURIComponent(op.project)}`}
                  className="hover:text-foreground transition-colors"
                >
                  {op.project}
                </Link>
              </>
            )}

            {op.session_name && (
              <>
                <span className="font-medium">Session</span>
                <Link
                  href={`/sessions?selected=${encodeURIComponent(op.session_name)}`}
                  className="font-mono hover:text-foreground transition-colors"
                >
                  {op.session_name}
                </Link>
              </>
            )}

            <span className="font-medium">Time</span>
            <span>
              {new Date(op.timestamp).toLocaleString(undefined, {
                month: "short",
                day: "numeric",
                hour: "numeric",
                minute: "2-digit",
                second: "2-digit",
              })}
            </span>
          </div>

          {/* Error message */}
          {!op.success && op.error_message && (
            <div className="flex items-start gap-2 rounded-md bg-destructive/10 border border-destructive/20 p-2">
              <AlertTriangle className="h-3.5 w-3.5 text-destructive shrink-0 mt-0.5" />
              <pre className="whitespace-pre-wrap break-all text-destructive/80 font-mono text-[11px] leading-relaxed">
                {op.error_message}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function AnalyticsPage() {
  const [days, setDays] = useState(7);
  const daysStr = String(days);

  const { data: opsData, loading, error } =
    useFetch<{ total: number; items: AnalyticsOperation[] }>(
      () => api.analyticsOperations({ days: daysStr, limit: "100" }),
      [daysStr],
    );

  return (
    <PageLayout
      title="Operations Log"
      filters={
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Range</span>
          <div className="flex gap-1">
            {DAY_PRESETS.map((p) => (
              <Button
                key={p.value}
                variant={days === p.value ? "default" : "outline"}
                size="sm"
                onClick={() => setDays(p.value)}
              >
                {p.label}
              </Button>
            ))}
          </div>
        </div>
      }
    >
      {loading && <SkeletonList count={10} />}

      {error && <ErrorState message="Failed to load operations" detail={error} />}

      {!loading && !error && (!opsData || opsData.items.length === 0) && (
        <EmptyState message="No operations recorded yet." detail="Operations are logged automatically as Cairn processes searches, embeddings, and LLM calls." />
      )}

      {!loading && !error && opsData && opsData.items.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">{opsData.total} total operations</p>
          <div className="rounded-md border border-border divide-y divide-border">
            {opsData.items.map((op) => (
              <OpRow key={op.id} op={op} />
            ))}
          </div>
        </div>
      )}
    </PageLayout>
  );
}
