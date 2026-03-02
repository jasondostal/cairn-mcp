"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type WorkItem, type GatedItem, type WorkItemStatus, type WorkItemDetail, type WorkspaceBackendInfo, type Deliverable } from "@/lib/api";
import { usePageFilters } from "@/lib/use-page-filters";
import { useLocalStorage } from "@/lib/use-local-storage";
import { useKeyboardNav } from "@/lib/use-keyboard-nav";
import { PageLayout } from "@/components/page-layout";
import { ErrorState } from "@/components/error-state";
import { EmptyState } from "@/components/empty-state";
import { SkeletonList } from "@/components/skeleton-list";
import { MultiSelect } from "@/components/ui/multi-select";
import { SingleSelect } from "@/components/ui/single-select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Button } from "@/components/ui/button";
import { TimeRangeFilter } from "@/components/time-range-filter";
import { Input } from "@/components/ui/input";
import { WorkItemRow } from "@/components/work-items/work-item-row";
import { WorkItemSheet } from "@/components/work-items/work-item-sheet";
import { CreateWorkItemDialog } from "@/components/work-items/create-dialog";
import { FileCheck, Hand, Plus } from "lucide-react";

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

const sortOptions: { value: string; label: string }[] = [
  { value: "default", label: "Default" },
  { value: "priority", label: "Priority" },
  { value: "updated", label: "Recently updated" },
  { value: "created", label: "Recently created" },
  { value: "done-bottom", label: "Done to bottom" },
];

const FILTER_MODES = [
  { value: "all", label: "All" },
  { value: "active", label: "Active" },
  { value: "active-recent", label: "Recent" },
  { value: "ready", label: "Ready" },
] as const;

const FILTER_ACCENT = "oklch(0.72 0.19 165)";

function FilterModeToggle({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <ToggleGroup
      type="single"
      variant="outline"
      size="sm"
      value={value}
      onValueChange={(v) => { if (v) onChange(v); }}
    >
      {FILTER_MODES.map((m) => (
        <ToggleGroupItem
          key={m.value}
          value={m.value}
          className="text-xs px-2.5 data-[state=on]:text-foreground"
          style={
            value === m.value
              ? {
                  backgroundColor: `color-mix(in oklch, ${FILTER_ACCENT} 15%, transparent)`,
                  borderColor: `color-mix(in oklch, ${FILTER_ACCENT} 40%, transparent)`,
                  color: FILTER_ACCENT,
                }
              : undefined
          }
        >
          {m.label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}

const TERMINAL_STATUSES = new Set(["done", "cancelled"]);

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
  const filters = usePageFilters({ defaultDays: 30 });
  const days = filters.days ?? 30;
  const [items, setItems] = useState<WorkItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [itemTypeFilter, setItemTypeFilter] = useState("");
  const [assigneeFilter, setAssigneeFilter] = useState("");
  const [readyIds, setReadyIds] = useState<Set<number>>(new Set());
  const [selectedItemId, setSelectedItemId] = useState<number | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [gatedItems, setGatedItems] = useState<GatedItem[]>([]);
  const [pendingReviews, setPendingReviews] = useState<Deliverable[]>([]);
  const [backends, setBackends] = useState<WorkspaceBackendInfo[]>([]);

  // Persisted UI state
  const [collapsed, setCollapsed] = useLocalStorage<number[]>("cairn-wi-collapsed", []);
  const [filterMode, setFilterMode] = useLocalStorage<string>("cairn-wi-filter", "all");
  const [sortMode, setSortMode] = useLocalStorage<string>("cairn-wi-sort", "default");

  const collapsedSet = useMemo(() => new Set(collapsed), [collapsed]);

  function toggleCollapse(id: number) {
    setCollapsed((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);
  }

  // Inline quick create
  const [quickTitle, setQuickTitle] = useState("");
  const [quickProject, setQuickProject] = useState("");
  const [quickCreating, setQuickCreating] = useState(false);
  const quickInputRef = useRef<HTMLInputElement>(null);

  const projectParam = filters.showAllProjects ? undefined : filters.projectFilter.join(",");

  // Parallel fetch: items + ready + gated in a single round trip
  const fetchAll = useCallback(() => {
    setLoading(true);
    setError(null);

    const opts: Record<string, string> = {};
    if (projectParam) opts.project = projectParam;
    if (statusFilter) opts.status = statusFilter;
    if (itemTypeFilter) opts.item_type = itemTypeFilter;
    opts.include_children = "true";
    opts.limit = "100";

    const promises: [
      Promise<{ items: WorkItem[] }>,
      Promise<{ items: { id: number }[] } | null>,
      Promise<{ items: GatedItem[] }>,
      Promise<{ items: Deliverable[] }>,
    ] = [
      api.workItems(opts),
      projectParam
        ? api.workItemReady(projectParam)
        : Promise.resolve(null),
      api.workItemsGated(projectParam ? { project: projectParam } : {}),
      api.pendingDeliverables(projectParam ? { project: projectParam } : {}),
    ];

    Promise.all(promises)
      .then(([itemsRes, readyRes, gatedRes, pendingRes]) => {
        setItems(itemsRes.items);
        if (readyRes) setReadyIds(new Set(readyRes.items.map((i) => i.id)));
        setGatedItems(gatedRes.items);
        setPendingReviews(pendingRes.items);
      })
      .catch((err) => setError(err?.message || "Failed to load work items"))
      .finally(() => setLoading(false));
  }, [projectParam, statusFilter, itemTypeFilter]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  // Fetch workspace backends once on mount
  useEffect(() => {
    api.workspaceBackends()
      .then((b) => setBackends(b.filter((be) => be.status === "healthy")))
      .catch(() => setBackends([]));
  }, []);

  // Polling with visibility awareness — all three endpoints in parallel
  useEffect(() => {
    let backoff = POLL_INTERVAL;

    function poll() {
      if (document.hidden) return;
      const opts: Record<string, string> = {
        ...(projectParam ? { project: projectParam } : {}),
        ...(statusFilter ? { status: statusFilter } : {}),
        ...(itemTypeFilter ? { item_type: itemTypeFilter } : {}),
        include_children: "true",
        limit: "100",
      };
      Promise.all([
        api.workItems(opts),
        projectParam
          ? api.workItemReady(projectParam)
          : Promise.resolve(null),
        api.workItemsGated(projectParam ? { project: projectParam } : {}),
        api.pendingDeliverables(projectParam ? { project: projectParam } : {}),
      ])
        .then(([itemsRes, readyRes, gatedRes, pendingRes]) => {
          setItems(itemsRes.items);
          if (readyRes) setReadyIds(new Set(readyRes.items.map((i) => i.id)));
          setGatedItems(gatedRes.items);
          setPendingReviews(pendingRes.items);
          backoff = POLL_INTERVAL;
        })
        .catch(() => {
          backoff = Math.min(backoff * 2, POLL_BACKOFF_MAX);
        });
    }

    const interval = setInterval(poll, POLL_INTERVAL);
    const handleVisibility = () => { if (!document.hidden) poll(); };
    document.addEventListener("visibilitychange", handleVisibility);

    return () => {
      clearInterval(interval);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [projectParam, statusFilter, itemTypeFilter]);

  // Derive assignee options from fetched items
  const assigneeOptions = useMemo(() => {
    const unique = new Set(items.map((i) => i.assignee).filter(Boolean) as string[]);
    return Array.from(unique).sort().map((a) => ({ value: a, label: a }));
  }, [items]);

  // Filter items based on filter mode + assignee, build tree, sort, flatten
  const rows = useMemo(() => {
    let filtered = items;
    const now = Date.now();

    // Assignee filter (client-side)
    if (assigneeFilter) {
      filtered = filtered.filter((i) => i.assignee === assigneeFilter);
    }

    if (filterMode === "active") {
      filtered = filtered.filter((i) => !TERMINAL_STATUSES.has(i.status));
    } else if (filterMode === "active-recent") {
      const recentMs = days * 24 * 60 * 60 * 1000;
      filtered = filtered.filter((i) => {
        if (!TERMINAL_STATUSES.has(i.status)) return true;
        const completedAt = i.completed_at ? new Date(i.completed_at).getTime() : 0;
        return now - completedAt < recentMs;
      });
    }

    let tree = buildTree(filtered);

    // Apply sort at root level
    if (sortMode === "done-bottom") {
      tree = sortCompletedToBottom(tree);
    } else if (sortMode === "priority") {
      tree = [...tree].sort((a, b) => b.item.priority - a.item.priority);
    } else if (sortMode === "updated") {
      tree = [...tree].sort((a, b) =>
        new Date(b.item.updated_at).getTime() - new Date(a.item.updated_at).getTime()
      );
    } else if (sortMode === "created") {
      tree = [...tree].sort((a, b) =>
        new Date(b.item.created_at).getTime() - new Date(a.item.created_at).getTime()
      );
    }

    return flattenTree(tree, collapsedSet);
  }, [items, filterMode, sortMode, assigneeFilter, collapsedSet, days]);

  // Filter for ready-only view mode
  const displayRows = filterMode === "ready"
    ? rows.filter((r) => readyIds.has(r.item.id))
    : rows;

  function openSheet(id: number) {
    setSelectedItemId(id);
    setSheetOpen(true);
  }

  function handleCreated() {
    fetchAll();
  }

  function handleAction() {
    fetchAll();
  }

  // Quick create handler
  async function handleQuickCreate() {
    const title = quickTitle.trim();
    if (!title) return;
    const project = projectParam || quickProject;
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

  // Keyboard navigation: j/k to move, Enter to open sheet
  const { activeIndex } = useKeyboardNav({
    itemCount: displayRows.length,
    onSelect: (i) => openSheet(displayRows[i].item.id),
    enabled: !sheetOpen && !createOpen,
  });

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
          <SingleSelect
            options={statusOptions}
            value={statusFilter}
            onValueChange={setStatusFilter}
            placeholder="All statuses"
          />
          <SingleSelect
            options={typeOptions}
            value={itemTypeFilter}
            onValueChange={setItemTypeFilter}
            placeholder="All types"
          />
          <SingleSelect
            options={assigneeOptions}
            value={assigneeFilter}
            onValueChange={setAssigneeFilter}
            placeholder="Assignee"
          />
          <FilterModeToggle value={filterMode} onChange={setFilterMode} />
          <TimeRangeFilter
            days={days}
            onChange={filters.setDays}
            presets={[
              { label: "7d", value: 7 },
              { label: "30d", value: 30 },
              { label: "90d", value: 90 },
            ]}
          />
          <SingleSelect
            options={sortOptions}
            value={sortMode}
            onValueChange={setSortMode}
            placeholder="Sort"
          />
        </div>
      }
    >
      {/* Needs Your Input — gated items */}
      {gatedItems.length > 0 && (
        <div className="mb-4">
          <div className="flex items-center gap-2 mb-2 text-sm font-medium text-status-gate">
            <Hand className="h-4 w-4" />
            Needs Your Input ({gatedItems.length})
          </div>
          <div className="rounded-md border border-status-gate/20 divide-y divide-border">
            {gatedItems.map((g) => (
              <div
                key={g.id}
                className="flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-accent/50 transition-colors cursor-pointer"
                onClick={() => openSheet(g.id)}
              >
                <Hand className="h-3 w-3 text-status-gate shrink-0" />
                <span className="font-mono text-xs text-muted-foreground shrink-0">{g.display_id}</span>
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

      {/* Needs Review — pending deliverables */}
      {pendingReviews.length > 0 && (
        <div className="mb-4">
          <div className="flex items-center gap-2 mb-2 text-sm font-medium text-status-wip">
            <FileCheck className="h-4 w-4" />
            Needs Review ({pendingReviews.length})
          </div>
          <div className="rounded-md border border-status-wip/20 divide-y divide-border">
            {pendingReviews.map((d) => (
              <div
                key={d.id}
                className="flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-accent/50 transition-colors cursor-pointer"
                onClick={() => openSheet(d.work_item_id)}
              >
                <FileCheck className="h-3 w-3 text-status-wip shrink-0" />
                <span className="font-mono text-xs text-muted-foreground shrink-0">v{d.version}</span>
                <span className="flex-1 truncate">{d.work_item_title || `Work item #${d.work_item_id}`}</span>
                {d.summary && (
                  <span className="text-xs text-muted-foreground truncate max-w-64">
                    {d.summary.slice(0, 80)}{d.summary.length > 80 ? "…" : ""}
                  </span>
                )}
                {d.project_name && (
                  <span className="font-mono text-xs text-muted-foreground/60 shrink-0">{d.project_name}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Quick capture — inline creation */}
      <div className="mb-3">
        <div className="flex gap-2">
          {filters.showAllProjects && (
            <SingleSelect
              options={filters.projectOptions}
              value={quickProject}
              onValueChange={setQuickProject}
              placeholder="Project"
              className="w-40"
            />
          )}
          <Input
            ref={quickInputRef}
            value={quickTitle}
            onChange={(e) => setQuickTitle(e.target.value)}
            placeholder="Quick create — type title, press Enter (N to focus)"
            className="h-8 text-sm flex-1"
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
          message={filterMode === "ready" ? "No dispatch-ready items." : "No work items found."}
          detail={filterMode === "ready" ? "All items are either assigned, blocked, or completed." : undefined}
        />
      )}

      {!loading && !filters.projectsLoading && !error && displayRows.length > 0 && (
        <div className="rounded-md border border-border divide-y divide-border">
          {displayRows.map((row, i) => (
            <WorkItemRow
              key={row.item.id}
              item={row.item}
              depth={row.depth}
              isLast={row.isLast}
              hasChildren={row.hasChildren}
              isCollapsed={row.isCollapsed}
              isActive={i === activeIndex}
              onToggleCollapse={toggleCollapse}
              showProject={filters.showAllProjects}
              readyIds={readyIds}
              onClick={() => openSheet(row.item.id)}
              backends={backends}
              onDispatch={handleAction}
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
        backends={backends}
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
