"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { api, type Memory } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useFetch } from "@/lib/use-fetch";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/error-state";
import { EmptyState } from "@/components/empty-state";
import { PageLayout } from "@/components/page-layout";
import { MemoryTypeBadge } from "@/components/memory-type-badge";
import { StatusDot } from "@/components/work-items/status-dot";
import { Tag, FileText, Star, Clock, Network, ArrowLeft, ArrowRight, Download, Link2 } from "lucide-react";

const RELATION_COLORS: Record<string, string> = {
  extends: "text-blue-400",
  contradicts: "text-red-400",
  implements: "text-green-400",
  depends_on: "text-amber-400",
  related: "text-muted-foreground",
};
import { triggerDownload } from "@/lib/download";

function formatMemoryAsMarkdown(memory: Memory): string {
  const lines = [
    "---",
    `id: ${memory.id}`,
    `type: ${memory.memory_type}`,
    `importance: ${memory.importance}`,
    `project: ${memory.project}`,
  ];
  if (memory.tags.length) lines.push(`tags: [${memory.tags.join(", ")}]`);
  lines.push(`created: ${memory.created_at}`);
  if (memory.session_name) lines.push(`session: ${memory.session_name}`);
  lines.push("---", "", memory.content);
  return lines.join("\n");
}

export default function MemoryDetail() {
  const params = useParams();
  const id = Number(params.id);
  const { data: memory, loading, error } = useFetch<Memory>(
    () => api.memory(id),
    [id]
  );
  const { data: linkedWI } = useFetch(
    () => api.memoryWorkItems(id),
    [id]
  );

  return (
    <PageLayout
      title={`Memory #${id}`}
      titleExtra={<>
        {memory && (
          <>
            <Badge variant="outline" className="font-mono">
              {memory.memory_type}
            </Badge>
            {!memory.is_active && <Badge variant="destructive">inactive</Badge>}
            <Button
              variant="outline"
              size="sm"
              onClick={() => triggerDownload(
                formatMemoryAsMarkdown(memory),
                `memory-${memory.id}.md`,
                "text/markdown"
              )}
            >
              <Download className="mr-1.5 h-4 w-4" />
              Download
            </Button>
          </>
        )}
        <Link href="/timeline">
          <Button variant="ghost" size="sm" className="gap-1.5">
            <ArrowLeft className="h-4 w-4" />
            Back
          </Button>
        </Link>
      </>}
    >
      {loading && (
        <div className="space-y-4 max-w-3xl">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-64" />
        </div>
      )}

      {!loading && error && <ErrorState message="Failed to load memory" detail={error} />}

      {!loading && !error && !memory && <EmptyState message="Memory not found." />}

      {!loading && !error && memory && (
        <div className="space-y-6 max-w-3xl">
          {memory.summary && (
            <Card>
              <CardHeader className="p-4 pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Summary
                </CardTitle>
              </CardHeader>
              <CardContent className="p-4 pt-0">
                <p className="text-sm">{memory.summary}</p>
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader className="p-4 pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Content
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4 pt-0">
              <p className="whitespace-pre-wrap text-sm leading-relaxed font-mono">
                {memory.content}
              </p>
            </CardContent>
          </Card>

          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Card>
              <CardContent className="flex items-center gap-3 p-4">
                <Star className="h-4 w-4 text-muted-foreground" />
                <div>
                  <p className="text-xs text-muted-foreground">Importance</p>
                  <p className="font-mono font-semibold">
                    {memory.importance.toFixed(2)}
                  </p>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="flex items-center gap-3 p-4">
                <Clock className="h-4 w-4 text-muted-foreground" />
                <div>
                  <p className="text-xs text-muted-foreground">Created</p>
                  <p className="text-sm font-medium">
                    {formatDate(memory.created_at)}
                  </p>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="flex items-center gap-3 p-4">
                <div className="h-4 w-4 text-center text-xs font-bold text-muted-foreground">
                  P
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Project</p>
                  <Link href={`/projects/${encodeURIComponent(memory.project)}`} className="text-sm font-medium text-primary hover:underline">{memory.project}</Link>
                </div>
              </CardContent>
            </Card>
            {memory.cluster && (
              <Card>
                <CardContent className="flex items-center gap-3 p-4">
                  <Network className="h-4 w-4 text-muted-foreground" />
                  <div>
                    <p className="text-xs text-muted-foreground">Cluster</p>
                    <Link href="/clusters" className="text-sm font-medium text-primary hover:underline">{memory.cluster.label}</Link>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>

          {memory.tags.length > 0 && (
            <div>
              <div className="mb-2 flex items-center gap-2 text-sm text-muted-foreground">
                <Tag className="h-4 w-4" />
                Tags
              </div>
              <div className="flex flex-wrap gap-1.5">
                {memory.tags.map((t) => (
                  <Badge key={t} variant="secondary">
                    {t}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {memory.auto_tags.length > 0 && (
            <div>
              <div className="mb-2 text-sm text-muted-foreground">Auto Tags</div>
              <div className="flex flex-wrap gap-1.5">
                {memory.auto_tags.map((t) => (
                  <Badge key={t} variant="outline">
                    {t}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {memory.relations && memory.relations.length > 0 && (
            <div>
              <div className="mb-2 flex items-center gap-2 text-sm text-muted-foreground">
                <Network className="h-4 w-4" />
                Relations
              </div>
              <div className="space-y-2">
                {memory.relations.map((rel, i) => (
                  <Link
                    key={`${rel.id}-${rel.relation}-${i}`}
                    href={`/memories/${rel.id}`}
                    className="flex items-start gap-2 text-sm group hover:bg-accent/50 rounded-md p-1.5 -mx-1.5 transition-colors"
                  >
                    {rel.direction === "outgoing" ? (
                      <ArrowRight className="h-3.5 w-3.5 mt-0.5 shrink-0 text-muted-foreground" />
                    ) : (
                      <ArrowLeft className="h-3.5 w-3.5 mt-0.5 shrink-0 text-muted-foreground" />
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className={`text-xs font-medium ${RELATION_COLORS[rel.relation] || "text-muted-foreground"}`}>
                          {rel.relation.replace("_", " ")}
                        </span>
                        <MemoryTypeBadge type={rel.memory_type} />
                        <span className="text-xs text-muted-foreground">
                          #{rel.id}
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground truncate">
                        {rel.summary}
                      </p>
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          )}

          {memory.related_files?.length > 0 && (
            <div>
              <div className="mb-2 flex items-center gap-2 text-sm text-muted-foreground">
                <FileText className="h-4 w-4" />
                Related Files
              </div>
              <div className="space-y-1">
                {memory.related_files.map((f) => (
                  <p key={f} className="font-mono text-sm">
                    {f}
                  </p>
                ))}
              </div>
            </div>
          )}

          {linkedWI && linkedWI.work_items.length > 0 && (
            <div>
              <div className="mb-2 flex items-center gap-2 text-sm text-muted-foreground">
                <Link2 className="h-4 w-4" />
                Linked Work Items
              </div>
              <div className="space-y-1.5">
                {linkedWI.work_items.map((wi) => (
                  <Link
                    key={wi.id}
                    href={`/work-items?id=${wi.id}`}
                    className="flex items-center gap-2 text-sm hover:bg-accent/50 rounded-md p-1.5 -mx-1.5 transition-colors"
                  >
                    <StatusDot status={wi.status as "open" | "ready" | "in_progress" | "blocked" | "done" | "cancelled"} />
                    <span className="font-mono text-xs text-muted-foreground">{wi.short_id}</span>
                    <span className="truncate">{wi.title}</span>
                  </Link>
                ))}
              </div>
            </div>
          )}

          {memory.session_name && (
            <p className="text-xs text-muted-foreground">
              Session: <Link href={`/sessions?selected=${encodeURIComponent(memory.session_name)}`} className="text-primary hover:underline">{memory.session_name}</Link>
            </p>
          )}

          {memory.inactive_reason && (
            <Card className="border-destructive/50">
              <CardContent className="p-4">
                <p className="text-sm text-destructive">
                  Inactive: {memory.inactive_reason}
                </p>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </PageLayout>
  );
}
