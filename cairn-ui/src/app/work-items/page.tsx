"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type WorkItem, type GatedItem, type WorkItemStatus, type WorkItemDetail } from "@/lib/api";
import { usePageFilters } from "@/lib/use-page-filters";
import { useLocalStorage } from "@/lib/use-local-storage";
import { PageLayout } from "@/components/page-layout";
import { ErrorState } from "@/components/error-state";
import { EmptyState } from "@/components/empty-state";
import { SkeletonList } from "@/components/skeleton-list";
import { MultiSelect } from "@/components/ui/multi-select";
import { SingleSelect } from "@/components/ui/single-select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { WorkItemRow } from "@/components/work-items/work-item-row";
import { WorkItemSheet } from "@/components/work-items/work-item-sheet";
import { CreateWorkItemDialog } from "@/components/work-items/create-dialog";
import { Hand, Plus } from "lucide-react";

const statusOptions: { value: string; label: string }[] = [
  { value: "open", label: "open" },
  { value: "ready", label: "ready" },
  { value: "in_progress", label: "in_progress" },
  { value: "blocked", label: "blocked" },
  { value: "done", label: "done" },
  { value: "cancelled", label: "cancelled" },
];

const typeOptions: { value: string; label: string }[] = [
  { value: "epic", label: "epic" },
  { value: "task", label: "task" },
  { value: "subtask", label: "subtask" },
];

const viewOptions: { value: string; label: string }[] = [
  { value: "all", label: "All items" },
  { value: "active", label: "Active" },
  { value: "active-recent", label: "Active + recent done" },
  { value: "bottom", label: "Done to bottom" },
  { value: "ready", label: "Ready only" },
];

const TERMINAL_STATUSES = new Set(["done", "cancelled"]);
const SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000;

// Build a tree from flat items list
interface TreeNode {
  item: WorkItem;
  children: TreeNode[];
}

function buildTree(items: WorkItem[]): TreeNode[] {
  const map = new Map<number, TreeNode>();
  const roots: TreeNode[] = [];

  // Create nodes
  for (const item of items) {
    map.set(item.id, { item, children: [] });
  }

  // Build hierarchy
  for (const item of items) {
    const node = map.get(item.id)!;
    if (item.parent_id && map.has(item.parent_id)) {
      map.get(item.parent_id)!.children.push(node);
    } else {
      roots.push(node);
    }
  }

  return roots;
}

// Recursively sort terminal-status children to the bottom at each level
function sortCompletedToBottom(nodes: TreeNode[]): TreeNode[] {
  return [...nodes]
    .sort((a, b) => {
      const aTerminal = TERMINAL_STATUSES.has(a.item.status) ? 1 : 0;
      const bTerminal = TERMINAL_STATUSES.has(b.item.status) ? 1 : 0;
      return aTerminal - bTerminal;
    })
    .map((node) =>
      node.children.length > 0
        ? { ...node, children: sortCompletedToBottom(node.children) }
        : node,
    );
}

interface FlatRow {
  item: WorkItem;
  depth: number;
  isLast: boolean;
  hasChildren: boolean;
  isCollapsed: boolean;
}

function flattenTree(nodes: TreeNode[], collapsedSet: Set<number>, depth = 0): FlatRow[] {
  const result: FlatRow[] = [];
  for (let i = 0; i < nodes.length; i++) {
    const node = nodes[i];
    const isLast = i === nodes.length - 1;
    const hasChildren = node.children.length > 0;
    const isCollapsed = collapsedSet.has(node.item.id);
    result.push({ item: node.item, depth, isLast, hasChildren, isCollapsed });
    if (hasChildren && !isCollapsed) {
      result.push(...flattenTree(node.children, collapsedSet, depth + 1));
    }
  }
  return result;
}

const POLL_INTERVAL = 10_000;
const POLL_BACKOFF_MAX = 60_000;

export default function WorkItemsPage() {
  const filters = usePageFilters();
  const [items, setItems] = useState<WorkItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string[]>([]);
  const [itemTypeFilter, setItemTypeFilter] = useState<string[]>([]);
  const [assigneeFilter, setAssigneeFilter] = useState("");
  const [readyIds, setReadyIds] = useState<Set<number>>(new Set());
  const [selectedItemId, setSelectedItemId] = useState<number | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [gatedItems, setGatedItems] = useState<GatedItem[]>([]);

  // Persisted UI state
  const [collapsed, setCollapsed] = useLocalStorage<number[]>("cairn-wi-collapsed", []);
  const [viewMode, setViewMode] = useLocalStorage<string>("cairn-wi-view", "all");

  const collapsedSet = useMemo(() => new Set(collapsed), [collapsed]);

  function toggleCollapse(id: number) {
    setCollapsed((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);
  }

  // Inline quick create
  const [quickTitle, setQuickTitle] = useState("");
  const [quickCreating, setQuickCreating] = useState(false);
  const quickInputRef = useRef<HTMLInputElement>(null);

  const projectParam = filters.showAllProjects ? undefined : filters.projectFilter.join(",");

  const fetchItems = useCallback(() => {
    setLoading(true);
    setError(null);

    const opts: Record<string, string> = {};
    if (projectParam) opts.project = projectParam;
    if (statusFilter.length > 0) opts.status = statusFilter[0]; // API takes single status
    if (itemTypeFilter.length > 0) opts.item_type = itemTypeFilter[0];
    if (assigneeFilter.trim()) opts.assignee = assigneeFilter.trim();
    opts.include_children = "true";
    opts.limit = "100";

    api.workItems(opts)
      .then((r) => setItems(r.items))
      .catch((err) => setError(err?.message || "Failed to load work items"))
      .finally(() => setLoading(false));
  }, [projectParam, statusFilter, itemTypeFilter, assigneeFilter]);

  // Fetch ready queue IDs for highlighting
  const fetchReady = useCallback(() => {
    if (!projectParam) return;
    api.workItemReady(projectParam)
      .then((r) => setReadyIds(new Set(r.items.map((i) => i.id))))
      .catch(() => {});
  }, [projectParam]);

  // Fetch gated items
  const fetchGated = useCallback(() => {
    api.workItemsGated(projectParam ? { project: projectParam } : {})
      .then((r) => setGatedItems(r.items))
      .catch(() => setGatedItems([]));
  }, [projectParam]);

  useEffect(() => { fetchItems(); }, [fetchItems]);
  useEffect(() => { fetchReady(); }, [fetchReady]);
  useEffect(() => { fetchGated(); }, [fetchGated]);

  // Polling with visibility awareness
  useEffect(() => {
    let interval: ReturnType<typeof setInterval>;
    let backoff = POLL_INTERVAL;

    function poll() {
      if (document.hidden) return;
      Promise.all([
        api.workItems({
          ...(projectParam ? { project: projectParam } : {}),
          ...(statusFilter.length > 0 ? { status: statusFilter[0] } : {}),
          ...(itemTypeFilter.length > 0 ? { item_type: itemTypeFilter[0] } : {}),
          ...(assigneeFilter.trim() ? { assignee: assigneeFilter.trim() } : {}),
          include_children: "true",
          limit: "100",
        }),
        api.workItemsGated(projectParam ? { project: projectParam } : {}),
      ])
        .then(([itemsRes, gatedRes]) => {
          setItems(itemsRes.items);
          setGatedItems(gatedRes.items);
          backoff = POLL_INTERVAL; // Reset on success
        })
        .catch(() => {
          backoff = Math.min(backoff * 2, POLL_BACKOFF_MAX); // Exponential backoff
        });
    }

    interval = setInterval(poll, POLL_INTERVAL);

    function handleVisibility() {
      if (!document.hidden) poll();
    }
    document.addEventListener("visibilitychange", handleVisibility);

    return () => {
      clearInterval(interval);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [projectParam, statusFilter, itemTypeFilter, assigneeFilter]);

  // Filter items based on view mode, build tree, flatten
  const rows = useMemo(() => {
    let filtered = items;
    const now = Date.now();

    if (viewMode === "active") {
      filtered = items.filter((i) => !TERMINAL_STATUSES.has(i.status));
    } else if (viewMode === "active-recent") {
      filtered = items.filter((i) => {
        if (!TERMINAL_STATUSES.has(i.status)) return true;
        const completedAt = i.completed_at ? new Date(i.completed_at).getTime() : 0;
        return now - completedAt < SEVEN_DAYS_MS;
      });
    }

    let tree = buildTree(filtered);

    if (viewMode === "bottom") {
      tree = sortCompletedToBottom(tree);
    }

    return flattenTree(tree, collapsedSet);
  }, [items, viewMode, collapsedSet]);

  // Filter for ready-only view mode
  const displayRows = viewMode === "ready"
    ? rows.filter((r) => readyIds.has(r.item.id))
    : rows;

  function openSheet(id: number) {
    setSelectedItemId(id);
    setSheetOpen(true);
  }

  function handleCreated() {
    fetchItems();
    fetchReady();
    fetchGated();
  }

  function handleAction() {
    fetchItems();
    fetchReady();
    fetchGated();
  }

  // Quick create handler
  async function handleQuickCreate() {
    const title = quickTitle.trim();
    if (!title) return;
    const project = projectParam || filters.projectOptions[0]?.value;
    if (!project) return;

    setQuickCreating(true);
    try {
      await api.workItemCreate({ project, title });
      setQuickTitle("");
      handleCreated();
    } catch { /* silent */ }
    finally { setQuickCreating(false); }
  }

  // Keyboard shortcut: N to focus quick create
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "n" && !e.metaKey && !e.ctrlKey && !e.altKey) {
        const target = e.target as HTMLElement;
        if (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable) return;
        e.preventDefault();
        quickInputRef.current?.focus();
      }
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, []);

  return (
    <PageLayout
      title="Work Items"
      titleExtra={
        <Button size="sm" variant="outline" onClick={() => setCreateOpen(true)}>
          <Plus className="mr-1 h-3.5 w-3.5" />
          New
        </Button>
      }
      filters={
        <div className="flex items-center gap-2 flex-wrap">
          <MultiSelect
            options={filters.projectOptions}
            value={filters.projectFilter}
            onValueChange={filters.setProjectFilter}
            placeholder="All projects"
            searchPlaceholder="Search projects…"
            maxCount={2}
          />
          <MultiSelect
            options={statusOptions}
            value={statusFilter}
            onValueChange={setStatusFilter}
            placeholder="All statuses"
            searchPlaceholder="Filter status…"
            maxCount={2}
          />
          <MultiSelect
            options={typeOptions}
            value={itemTypeFilter}
            onValueChange={setItemTypeFilter}
            placeholder="All types"
            searchPlaceholder="Filter type…"
            maxCount={2}
          />
          <Input
            placeholder="Assignee…"
            value={assigneeFilter}
            onChange={(e) => setAssigneeFilter(e.target.value)}
            className="h-8 w-32 text-sm"
          />
          <SingleSelect
            options={viewOptions}
            value={viewMode}
            onValueChange={setViewMode}
            placeholder="View"
          />
        </div>
      }
    >
      {/* Needs Your Input — gated items */}
      {gatedItems.length > 0 && (
        <div className="mb-4">
          <div className="flex items-center gap-2 mb-2 text-sm font-medium text-[oklch(0.627_0.265_304)]">
            <Hand className="h-4 w-4" />
            Needs Your Input ({gatedItems.length})
          </div>
          <div className="rounded-md border border-[oklch(0.627_0.265_304)]/20 divide-y divide-border">
            {gatedItems.map((g) => (
              <div
                key={g.id}
                className="flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-accent/50 transition-colors cursor-pointer"
                onClick={() => openSheet(g.id)}
              >
                <Hand className="h-3 w-3 text-[oklch(0.627_0.265_304)] shrink-0" />
                <span className="font-mono text-xs text-muted-foreground shrink-0">{g.short_id}</span>
                <span className="flex-1 truncate">{g.title}</span>
                {typeof g.gate_data?.question === "string" && (
                  <span className="text-xs text-muted-foreground truncate max-w-48">
                    {g.gate_data.question}
                  </span>
                )}
                <span className="font-mono text-xs text-muted-foreground/60 shrink-0">{g.project}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Quick capture — inline creation */}
      <div className="mb-3">
        <div className="flex gap-2">
          <Input
            ref={quickInputRef}
            value={quickTitle}
            onChange={(e) => setQuickTitle(e.target.value)}
            placeholder="Quick create — type title, press Enter (N to focus)"
            className="h-8 text-sm"
            disabled={quickCreating}
            onKeyDown={(e) => {
              if (e.key === "Enter" && quickTitle.trim()) handleQuickCreate();
              if (e.key === "Escape") {
                setQuickTitle("");
                (e.target as HTMLElement).blur();
              }
            }}
          />
        </div>
      </div>

      {(loading || filters.projectsLoading) && <SkeletonList count={6} height="h-8" />}

      {error && <ErrorState message="Failed to load work items" detail={error} />}

      {!loading && !filters.projectsLoading && !error && displayRows.length === 0 && (
        <EmptyState
          message={viewMode === "ready" ? "No dispatch-ready items." : "No work items found."}
          detail={viewMode === "ready" ? "All items are either assigned, blocked, or completed." : undefined}
        />
      )}

      {!loading && !filters.projectsLoading && !error && displayRows.length > 0 && (
        <div className="rounded-md border border-border divide-y divide-border">
          {displayRows.map((row) => (
            <WorkItemRow
              key={row.item.id}
              item={row.item}
              depth={row.depth}
              isLast={row.isLast}
              hasChildren={row.hasChildren}
              isCollapsed={row.isCollapsed}
              onToggleCollapse={toggleCollapse}
              showProject={filters.showAllProjects}
              readyIds={readyIds}
              onClick={() => openSheet(row.item.id)}
            />
          ))}
        </div>
      )}

      <WorkItemSheet
        itemId={selectedItemId}
        open={sheetOpen}
        onOpenChange={setSheetOpen}
        onAction={handleAction}
        onNavigate={(id) => {
          setSelectedItemId(id);
        }}
      />

      <CreateWorkItemDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        projects={filters.projectOptions}
        defaultProject={filters.projectFilter[0]}
        onCreated={handleCreated}
      />
    </PageLayout>
  );
}
