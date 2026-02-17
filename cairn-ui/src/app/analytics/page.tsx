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

const DAY_PRESETS = [
  { label: "7d", value: 7 },
  { label: "30d", value: 30 },
  { label: "90d", value: 90 },
] as const;

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
              <div key={op.id} className="flex items-center gap-3 px-3 py-1.5 text-xs">
                <Badge variant={op.success ? "secondary" : "destructive"} className="text-[10px] shrink-0">
                  {op.success ? "OK" : "ERR"}
                </Badge>
                <span className="font-mono font-medium truncate max-w-[160px]">{op.operation}</span>
                {op.project && (
                  <Link href={`/projects/${encodeURIComponent(op.project)}`} className="text-muted-foreground hover:text-foreground truncate max-w-[120px] transition-colors">
                    {op.project}
                  </Link>
                )}
                {op.model && (
                  <span className="font-mono text-muted-foreground truncate max-w-[160px] hidden lg:inline">{op.model}</span>
                )}
                <span className="tabular-nums text-muted-foreground ml-auto shrink-0">
                  {op.latency_ms.toFixed(0)}ms
                </span>
                {(op.tokens_in > 0 || op.tokens_out > 0) && (
                  <span className="tabular-nums text-muted-foreground shrink-0">
                    {op.tokens_in}/{op.tokens_out}t
                  </span>
                )}
                {op.session_name && (
                  <Link href={`/sessions`} className="font-mono text-muted-foreground/60 hover:text-foreground truncate max-w-[100px] hidden xl:inline transition-colors" title={op.session_name}>
                    {op.session_name.slice(0, 12)}
                  </Link>
                )}
                <span className="text-muted-foreground shrink-0">
                  {new Date(op.timestamp).toLocaleTimeString()}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </PageLayout>
  );
}
