"use client";

import { useEffect, useState } from "react";
import { api, type Memory } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { MemoryTypeBadge } from "@/components/memory-type-badge";
import { ImportanceBadge } from "@/components/importance-badge";
import { Tag, FileText, Network } from "lucide-react";

interface MemorySheetProps {
  memoryId: number | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function MemorySheet({ memoryId, open, onOpenChange }: MemorySheetProps) {
  const [memory, setMemory] = useState<Memory | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!memoryId || !open) return;
    setLoading(true);
    setError(null);
    api
      .memory(memoryId)
      .then(setMemory)
      .catch((err) => setError(err?.message || "Failed to load memory"))
      .finally(() => setLoading(false));
  }, [memoryId, open]);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="overflow-y-auto">
        {loading && (
          <SheetHeader>
            <Skeleton className="h-6 w-48" />
            <Skeleton className="h-4 w-32" />
            <div className="space-y-2 pt-4">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-3/4" />
            </div>
          </SheetHeader>
        )}

        {error && (
          <SheetHeader>
            <SheetTitle>Error</SheetTitle>
            <SheetDescription>{error}</SheetDescription>
          </SheetHeader>
        )}

        {!loading && !error && memory && (
          <>
            <SheetHeader>
              <div className="flex items-center gap-2">
                <MemoryTypeBadge type={memory.memory_type} />
                <span className="text-xs text-muted-foreground">
                  #{memory.id}
                </span>
              </div>
              <SheetTitle className="text-base">
                {memory.summary || "Memory #" + memory.id}
              </SheetTitle>
              <SheetDescription>
                {memory.project} &middot;{" "}
                {formatDateTime(memory.created_at)}
              </SheetDescription>
            </SheetHeader>

            <div className="space-y-4 px-4 pb-4">
              {/* Stats */}
              <div className="flex items-center gap-4 text-sm">
                <ImportanceBadge importance={memory.importance} />
                {!memory.is_active && (
                  <Badge variant="destructive" className="text-xs">
                    Inactive
                  </Badge>
                )}
              </div>

              <Separator />

              {/* Content */}
              <div>
                <h3 className="mb-2 text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  Content
                </h3>
                <p className="whitespace-pre-wrap text-sm font-mono leading-relaxed">
                  {memory.content}
                </p>
              </div>

              {/* Tags */}
              {(memory.tags.length > 0 || memory.auto_tags.length > 0) && (
                <>
                  <Separator />
                  <div>
                    <h3 className="mb-2 text-xs font-medium text-muted-foreground uppercase tracking-wider flex items-center gap-1">
                      <Tag className="h-3 w-3" /> Tags
                    </h3>
                    <div className="flex flex-wrap gap-1.5">
                      {memory.tags.map((t) => (
                        <Badge key={t} variant="secondary" className="text-xs">
                          {t}
                        </Badge>
                      ))}
                      {memory.auto_tags.map((t) => (
                        <Badge key={t} variant="outline" className="text-xs">
                          {t}
                        </Badge>
                      ))}
                    </div>
                  </div>
                </>
              )}

              {/* Related Files */}
              {memory.related_files.length > 0 && (
                <>
                  <Separator />
                  <div>
                    <h3 className="mb-2 text-xs font-medium text-muted-foreground uppercase tracking-wider flex items-center gap-1">
                      <FileText className="h-3 w-3" /> Related Files
                    </h3>
                    <div className="space-y-1">
                      {memory.related_files.map((f) => (
                        <p key={f} className="font-mono text-xs text-muted-foreground">
                          {f}
                        </p>
                      ))}
                    </div>
                  </div>
                </>
              )}

              {/* Cluster */}
              {memory.cluster && (
                <>
                  <Separator />
                  <div>
                    <h3 className="mb-2 text-xs font-medium text-muted-foreground uppercase tracking-wider flex items-center gap-1">
                      <Network className="h-3 w-3" /> Cluster
                    </h3>
                    <p className="text-sm">
                      {memory.cluster.label}
                      <span className="ml-2 text-xs text-muted-foreground">
                        ({memory.cluster.size} members)
                      </span>
                    </p>
                  </div>
                </>
              )}

              {/* Metadata */}
              <Separator />
              <div className="space-y-1 text-xs text-muted-foreground">
                {memory.session_name && (
                  <p>Session: {memory.session_name}</p>
                )}
                <p>Created: {formatDateTime(memory.created_at)}</p>
                <p>Updated: {formatDateTime(memory.updated_at)}</p>
                {memory.inactive_reason && (
                  <p>Inactive reason: {memory.inactive_reason}</p>
                )}
              </div>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
