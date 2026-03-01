"use client";

import { useEffect, useState, useCallback } from "react";
import { api, type WorkingMemoryItem, invalidateCache } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { usePageFilters } from "@/lib/use-page-filters";
import { PageFilters, DenseToggle } from "@/components/page-filters";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/error-state";
import { PaginatedList } from "@/components/paginated-list";
import { SkeletonList } from "@/components/skeleton-list";
import { EmptyState } from "@/components/empty-state";
import { PageLayout } from "@/components/page-layout";
import { Lightbulb, Pin, Zap, Archive, ArrowRight, Plus } from "lucide-react";

const TYPE_STYLES: Record<string, { label: string; variant: "default" | "secondary" | "destructive" | "outline" }> = {
  hypothesis: { label: "Hypothesis", variant: "default" },
  question: { label: "Question", variant: "secondary" },
  tension: { label: "Tension", variant: "destructive" },
  connection: { label: "Connection", variant: "outline" },
  thread: { label: "Thread", variant: "secondary" },
  intuition: { label: "Intuition", variant: "default" },
};

function SalienceBar({ salience }: { salience: number }) {
  return (
    <div className="w-1 rounded-full self-stretch mr-3 shrink-0" style={{
      backgroundColor: `hsl(45, 100%, 50%)`,
      opacity: Math.max(0.15, salience),
    }} />
  );
}

function ItemCard({
  item,
  onAction,
}: {
  item: WorkingMemoryItem;
  onAction: (id: number, action: string) => void;
}) {
  const typeStyle = TYPE_STYLES[item.item_type] || TYPE_STYLES.thread;

  return (
    <Card className="transition-colors hover:border-primary/30">
      <div className="flex">
        <SalienceBar salience={item.salience} />
        <div className="flex-1 min-w-0">
          <CardHeader className="p-4 pb-2">
            <div className="flex items-center gap-2">
              <Lightbulb className="h-4 w-4 text-muted-foreground shrink-0" />
              <Badge variant={typeStyle.variant} className="text-xs shrink-0">
                {typeStyle.label}
              </Badge>
              {item.pinned && <Pin className="h-3 w-3 text-amber-500 shrink-0" />}
              <span className="text-xs text-muted-foreground ml-auto shrink-0">
                {(item.salience * 100).toFixed(0)}%
              </span>
            </div>
          </CardHeader>
          <CardContent className="p-4 pt-0">
            <p className="text-sm whitespace-pre-wrap mb-2">{item.content}</p>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              {item.author && <span>{item.author}</span>}
              <span>{formatDate(item.created_at)}</span>
              <div className="ml-auto flex gap-1">
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 w-6 p-0"
                  title="Boost salience"
                  onClick={(e) => { e.preventDefault(); onAction(item.id, "boost"); }}
                >
                  <Zap className="h-3 w-3" />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 w-6 p-0"
                  title={item.pinned ? "Unpin" : "Pin"}
                  onClick={(e) => { e.preventDefault(); onAction(item.id, item.pinned ? "unpin" : "pin"); }}
                >
                  <Pin className="h-3 w-3" />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 w-6 p-0"
                  title="Archive"
                  onClick={(e) => { e.preventDefault(); onAction(item.id, "archive"); }}
                >
                  <Archive className="h-3 w-3" />
                </Button>
              </div>
            </div>
          </CardContent>
        </div>
      </div>
    </Card>
  );
}

function ItemDenseRow({
  item,
  onAction,
}: {
  item: WorkingMemoryItem;
  onAction: (id: number, action: string) => void;
}) {
  const typeStyle = TYPE_STYLES[item.item_type] || TYPE_STYLES.thread;

  return (
    <div className="flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-accent/50 transition-colors">
      <div
        className="w-1 h-4 rounded-full shrink-0"
        style={{
          backgroundColor: `hsl(45, 100%, 50%)`,
          opacity: Math.max(0.15, item.salience),
        }}
      />
      <Lightbulb className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
      <Badge variant={typeStyle.variant} className="text-xs shrink-0">
        {typeStyle.label}
      </Badge>
      {item.pinned && <Pin className="h-3 w-3 text-amber-500 shrink-0" />}
      <span className="flex-1 truncate">{item.content}</span>
      <span className="text-xs text-muted-foreground shrink-0">
        {(item.salience * 100).toFixed(0)}%
      </span>
      {item.author && (
        <span className="text-xs text-muted-foreground shrink-0">{item.author}</span>
      )}
      <span className="text-xs text-muted-foreground shrink-0">{formatDate(item.created_at)}</span>
      <div className="flex gap-0.5 shrink-0">
        <Button variant="ghost" size="sm" className="h-5 w-5 p-0" title="Boost"
          onClick={() => onAction(item.id, "boost")}>
          <Zap className="h-2.5 w-2.5" />
        </Button>
        <Button variant="ghost" size="sm" className="h-5 w-5 p-0" title={item.pinned ? "Unpin" : "Pin"}
          onClick={() => onAction(item.id, item.pinned ? "unpin" : "pin")}>
          <Pin className="h-2.5 w-2.5" />
        </Button>
        <Button variant="ghost" size="sm" className="h-5 w-5 p-0" title="Archive"
          onClick={() => onAction(item.id, "archive")}>
          <Archive className="h-2.5 w-2.5" />
        </Button>
      </div>
    </div>
  );
}

function CaptureForm({
  project,
  onCaptured,
}: {
  project: string;
  onCaptured: () => void;
}) {
  const [content, setContent] = useState("");
  const [itemType, setItemType] = useState("thread");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!content.trim()) return;
    setSubmitting(true);
    try {
      await api.workingMemoryCapture(project, {
        content: content.trim(),
        item_type: itemType,
        author: "human",
      });
      setContent("");
      invalidateCache("/working-memory");
      onCaptured();
    } catch {
      // error handling via UI
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card className="mb-4">
      <form onSubmit={handleSubmit} className="p-4">
        <div className="flex gap-2 items-start">
          <textarea
            className="flex-1 min-h-[60px] resize-none rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            placeholder="What's on your mind? A hypothesis, question, tension, intuition..."
            value={content}
            onChange={(e) => setContent(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                handleSubmit(e);
              }
            }}
          />
          <div className="flex flex-col gap-2">
            <select
              className="rounded-md border border-input bg-background px-2 py-1 text-xs"
              value={itemType}
              onChange={(e) => setItemType(e.target.value)}
            >
              <option value="thread">Thread</option>
              <option value="hypothesis">Hypothesis</option>
              <option value="question">Question</option>
              <option value="tension">Tension</option>
              <option value="connection">Connection</option>
              <option value="intuition">Intuition</option>
            </select>
            <Button type="submit" size="sm" disabled={!content.trim() || submitting}>
              <Plus className="h-3 w-3 mr-1" />
              Capture
            </Button>
          </div>
        </div>
      </form>
    </Card>
  );
}

export default function MindPage() {
  const filters = usePageFilters();
  const [items, setItems] = useState<WorkingMemoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const project = filters.showAllProjects ? undefined : filters.projectFilter.join(",");

  const loadItems = useCallback(() => {
    if (!project) return;
    setLoading(true);
    setError(null);
    api
      .workingMemory(project)
      .then((r) => setItems(r.items))
      .catch((err) => setError(err?.message || "Failed to load working memory"))
      .finally(() => setLoading(false));
  }, [project]);

  useEffect(() => {
    loadItems();
  }, [loadItems]);

  const handleAction = async (id: number, action: string) => {
    try {
      if (action === "boost") await api.workingMemoryBoost(id);
      else if (action === "pin") await api.workingMemoryPin(id);
      else if (action === "unpin") await api.workingMemoryUnpin(id);
      else if (action === "archive") await api.workingMemoryArchive(id);
      invalidateCache("/working-memory");
      loadItems();
    } catch {
      // swallow
    }
  };

  return (
    <PageLayout
      title="Mind"
      titleExtra={<DenseToggle dense={filters.dense} onToggle={() => filters.setDense((d) => !d)} />}
      filters={<PageFilters filters={filters} />}
    >
      {project && <CaptureForm project={project} onCaptured={loadItems} />}

      {(loading || filters.projectsLoading) && <SkeletonList count={4} />}

      {error && <ErrorState message="Failed to load working memory" detail={error} />}

      {!loading && !filters.projectsLoading && !error && items.length === 0 && (
        <EmptyState
          message={filters.showAllProjects
            ? "No active thoughts yet."
            : `No active thoughts for ${filters.projectFilter.join(", ")}.`}
          detail="Working memory stores half-formed hypotheses, questions, tensions, and intuitions that persist across sessions."
        />
      )}

      {!loading && !filters.projectsLoading && !error && items.length > 0 && (
        filters.dense ? (
          <div className="rounded-md border border-border divide-y divide-border">
            {items.map((item) => (
              <ItemDenseRow key={item.id} item={item} onAction={handleAction} />
            ))}
          </div>
        ) : (
          <PaginatedList
            items={items}
            noun="thoughts"
            keyExtractor={(item) => item.id}
            renderItem={(item) => <ItemCard item={item} onAction={handleAction} />}
          />
        )
      )}
    </PageLayout>
  );
}
