"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type WorkItem, type WorkItemStatus, type WorkItemDetail } from "@/lib/api";
import { usePageFilters } from "@/lib/use-page-filters";
import { PageFilters } from "@/components/page-filters";
import { PageLayout } from "@/components/page-layout";
import { ErrorState } from "@/components/error-state";
import { EmptyState } from "@/components/empty-state";
import { SkeletonList } from "@/components/skeleton-list";
import { MultiSelect } from "@/components/ui/multi-select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { WorkItemRow } from "@/components/work-items/work-item-row";
import { WorkItemSheet } from "@/components/work-items/work-item-sheet";
import { CreateWorkItemDialog } from "@/components/work-items/create-dialog";
import { Plus, Zap } from "lucide-react";

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

function flattenTree(nodes: TreeNode[], depth = 0): Array<{ item: WorkItem; depth: number; isLast: boolean }> {
  const result: Array<{ item: WorkItem; depth: number; isLast: boolean }> = [];
  for (let i = 0; i < nodes.length; i++) {
    const node = nodes[i];
    const isLast = i === nodes.length - 1;
    result.push({ item: node.item, depth, isLast });
    if (node.children.length > 0) {
      result.push(...flattenTree(node.children, depth + 1));
    }
  }
  return result;
}

export default function WorkItemsPage() {
  const filters = usePageFilters();
  const [items, setItems] = useState<WorkItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string[]>([]);
  const [itemTypeFilter, setItemTypeFilter] = useState<string[]>([]);
  const [assigneeFilter, setAssigneeFilter] = useState("");
  const [readyOnly, setReadyOnly] = useState(false);
  const [readyIds, setReadyIds] = useState<Set<number>>(new Set());
  const [selectedItemId, setSelectedItemId] = useState<number | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);

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

  useEffect(() => { fetchItems(); }, [fetchItems]);
  useEffect(() => { fetchReady(); }, [fetchReady]);

  // Build tree and flatten
  const rows = useMemo(() => {
    const tree = buildTree(items);
    return flattenTree(tree);
  }, [items]);

  // Filter for ready-only mode
  const displayRows = readyOnly
    ? rows.filter((r) => readyIds.has(r.item.id))
    : rows;

  function openSheet(id: number) {
    setSelectedItemId(id);
    setSheetOpen(true);
  }

  function handleCreated() {
    fetchItems();
    fetchReady();
  }

  function handleAction() {
    fetchItems();
    fetchReady();
  }

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
          <Button
            variant={readyOnly ? "default" : "outline"}
            size="sm"
            onClick={() => setReadyOnly(!readyOnly)}
            title="Show only dispatch-ready items"
          >
            <Zap className="mr-1 h-3.5 w-3.5" />
            Ready
          </Button>
        </div>
      }
    >
      {(loading || filters.projectsLoading) && <SkeletonList count={6} height="h-8" />}

      {error && <ErrorState message="Failed to load work items" detail={error} />}

      {!loading && !filters.projectsLoading && !error && displayRows.length === 0 && (
        <EmptyState
          message={readyOnly ? "No dispatch-ready items." : "No work items found."}
          detail={readyOnly ? "All items are either assigned, blocked, or completed." : undefined}
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
