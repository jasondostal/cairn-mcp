"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api, type CairnDetail, type CairnStone } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useFetch } from "@/lib/use-fetch";
import { useMemorySheet } from "@/lib/use-memory-sheet";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/error-state";
import { MemorySheet } from "@/components/memory-sheet";
import { MemoryTypeBadge } from "@/components/memory-type-badge";
import { ImportanceBadge } from "@/components/importance-badge";
import { PageLayout } from "@/components/page-layout";
import { EmptyState } from "@/components/empty-state";
import {
  ArrowLeft,
  Archive,
  Layers,
  ChevronDown,
  ChevronRight,
  Tag,
} from "lucide-react";

function StoneCard({
  stone,
  onClick,
}: {
  stone: CairnStone;
  onClick: () => void;
}) {
  return (
    <Card
      className="cursor-pointer transition-colors hover:bg-accent/50"
      onClick={onClick}
    >
      <CardContent className="p-3 space-y-1.5">
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm">{stone.summary}</p>
          <ImportanceBadge importance={stone.importance} />
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <MemoryTypeBadge type={stone.memory_type} />
          <span>{formatDate(stone.created_at)}</span>
        </div>
        {stone.tags.length > 0 && (
          <div className="flex items-center gap-1 flex-wrap">
            <Tag className="h-3 w-3 text-muted-foreground" />
            {stone.tags.map((t) => (
              <Badge key={t} variant="secondary" className="text-xs">
                {t}
              </Badge>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function EventTimeline({ events }: { events: Array<Record<string, unknown>> }) {
  const [open, setOpen] = useState(false);

  return (
    <div>
      <Button
        variant="ghost"
        size="sm"
        className="mb-2 gap-1.5"
        onClick={() => setOpen(!open)}
      >
        {open ? (
          <ChevronDown className="h-4 w-4" />
        ) : (
          <ChevronRight className="h-4 w-4" />
        )}
        Event Timeline ({events.length} events)
      </Button>
      {open && (
        <Card>
          <CardContent className="p-3">
            <div className="max-h-96 overflow-y-auto space-y-0.5 font-mono text-xs">
              {events.map((event, i) => {
                const ts = event.timestamp || event.ts || event.time || "";
                const type = event.type || event.event || "event";
                const detail =
                  event.detail ||
                  event.message ||
                  event.description ||
                  "";
                return (
                  <div key={i} className="text-muted-foreground">
                    {ts ? (
                      <span>[{String(ts)}] </span>
                    ) : null}
                    <span className="text-foreground">{String(type)}</span>
                    {detail ? `: ${String(detail)}` : ""}
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export default function CairnDetailPage() {
  const params = useParams();
  const id = Number(params.id);
  const { data: detail, loading, error } = useFetch<CairnDetail>(
    () => api.cairnDetail(id),
    [id]
  );
  const { sheetId, sheetOpen, setSheetOpen, openSheet } = useMemorySheet();

  return (
    <PageLayout
      title={detail?.title ?? "Cairn"}
      titleExtra={
        <Link href="/cairns">
          <Button variant="ghost" size="sm" className="gap-1.5">
            <ArrowLeft className="h-4 w-4" />
            Back
          </Button>
        </Link>
      }
    >
      {loading && (
        <div className="space-y-4">
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-40" />
        </div>
      )}

      {!loading && error && <ErrorState message="Failed to load cairn" detail={error} />}

      {!loading && !error && !detail && <EmptyState message="Cairn not found." />}

      {!loading && !error && detail && (
        <div className="space-y-6 max-w-3xl">
          <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <Link href={`/sessions?selected=${encodeURIComponent(detail.session_name)}`}>
              <Badge variant="outline" className="hover:bg-accent cursor-pointer">{detail.session_name}</Badge>
            </Link>
            <Link href={`/projects/${encodeURIComponent(detail.project)}`} className="text-primary hover:underline">{detail.project}</Link>
            <span>&middot;</span>
            <span className="flex items-center gap-1">
              <Layers className="h-3.5 w-3.5" />
              {detail.memory_count} {detail.memory_count === 1 ? "stone" : "stones"}
            </span>
            <span>&middot;</span>
            <span>{formatDate(detail.set_at)}</span>
            {detail.is_compressed && (
              <Badge variant="secondary" className="text-xs">
                <Archive className="mr-1 h-3 w-3" />
                compressed
              </Badge>
            )}
          </div>

          {detail.narrative && (
            <div>
              <h2 className="mb-2 text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Narrative
              </h2>
              <Card>
                <CardContent className="p-4">
                  <div className="prose prose-sm dark:prose-invert max-w-none whitespace-pre-wrap text-sm leading-relaxed">
                    {detail.narrative}
                  </div>
                </CardContent>
              </Card>
            </div>
          )}

          <Separator />

          <div>
            <h2 className="mb-3 text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Linked Stones ({detail.stones.length})
            </h2>
            {detail.stones.length === 0 ? (
              <EmptyState message="No linked stones." />
            ) : (
              <div className="space-y-2">
                {detail.stones.map((stone) => (
                  <StoneCard
                    key={stone.id}
                    stone={stone}
                    onClick={() => openSheet(stone.id)}
                  />
                ))}
              </div>
            )}
          </div>

          {detail.events && !detail.is_compressed && detail.events.length > 0 && (
            <>
              <Separator />
              <div>
                <h2 className="mb-2 text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  Events
                </h2>
                <EventTimeline events={detail.events} />
              </div>
            </>
          )}

          {detail.is_compressed && detail.events === null && (
            <>
              <Separator />
              <p className="text-sm text-muted-foreground italic">
                Events compressed.
              </p>
            </>
          )}
        </div>
      )}

      <MemorySheet
        memoryId={sheetId}
        open={sheetOpen}
        onOpenChange={setSheetOpen}
      />
    </PageLayout>
  );
}
