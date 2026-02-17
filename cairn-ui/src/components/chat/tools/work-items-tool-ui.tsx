"use client";

import type { ToolCallMessagePartProps } from "@assistant-ui/react";
import { ListChecks, Loader2, Plus, CheckCircle2 } from "lucide-react";

/* ---------- list_work_items ---------- */

interface WorkItemSummary {
  id: number;
  short_id: string;
  title: string;
  item_type: string;
  priority: number;
  status: string;
  assignee: string | null;
}

interface ListOutput {
  count: number;
  items: WorkItemSummary[];
}

type ListArgs = {
  project: string;
  status?: string;
  item_type?: string;
};

const statusColors: Record<string, string> = {
  open: "text-blue-400",
  ready: "text-emerald-400",
  in_progress: "text-amber-400",
  blocked: "text-red-400",
  done: "text-muted-foreground",
  cancelled: "text-muted-foreground",
};

export function ListWorkItemsToolUI({
  args,
  result,
  status,
}: ToolCallMessagePartProps<ListArgs, ListOutput>) {
  const isRunning = status.type === "running";

  return (
    <div className="my-1.5 rounded-md border border-border/50 bg-background/30 overflow-hidden">
      <div className="flex items-center gap-1.5 px-3 py-1.5 bg-muted/30 border-b border-border/30">
        <ListChecks className="h-3 w-3 text-muted-foreground" />
        <span className="text-xs font-medium">work items</span>
        <span className="text-xs text-muted-foreground">{args.project}</span>
        {args.status && (
          <span className="text-[10px] text-muted-foreground">
            ({args.status})
          </span>
        )}
        {isRunning && (
          <Loader2 className="ml-auto h-3 w-3 animate-spin text-muted-foreground" />
        )}
        {result && (
          <span className="ml-auto text-[10px] text-muted-foreground">
            {result.count} item{result.count !== 1 ? "s" : ""}
          </span>
        )}
      </div>
      {result && result.items.length > 0 && (
        <div className="divide-y divide-border/30">
          {result.items.slice(0, 8).map((item) => (
            <div
              key={item.id}
              className="flex items-center gap-2 px-3 py-1.5 text-xs"
            >
              <span
                className={`text-[10px] font-mono ${statusColors[item.status] ?? "text-muted-foreground"}`}
              >
                {item.short_id}
              </span>
              <span className="rounded bg-muted px-1 py-0.5 text-[9px]">
                {item.item_type}
              </span>
              <span className="flex-1 truncate text-foreground/80">
                {item.title}
              </span>
              <span
                className={`text-[10px] ${statusColors[item.status] ?? "text-muted-foreground"}`}
              >
                {item.status}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ---------- create_work_item ---------- */

interface CreateOutput {
  created: boolean;
  id: number;
  short_id: string;
  project: string;
  title: string;
}

type CreateArgs = {
  project: string;
  title: string;
  description?: string;
  item_type?: string;
  priority?: number;
};

export function CreateWorkItemToolUI({
  args,
  result,
  status,
}: ToolCallMessagePartProps<CreateArgs, CreateOutput>) {
  const isRunning = status.type === "running";

  return (
    <div className="my-1.5 rounded-md border border-border/50 bg-background/30 overflow-hidden">
      <div className="flex items-center gap-1.5 px-3 py-1.5 bg-muted/30">
        {isRunning ? (
          <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
        ) : (
          <Plus className="h-3 w-3 text-muted-foreground" />
        )}
        <span className="text-xs font-medium">create work item</span>
        <span className="text-xs text-muted-foreground truncate">
          &quot;{args.title}&quot;
        </span>
        {result?.created && (
          <div className="ml-auto flex items-center gap-1 text-[10px] text-green-400">
            <CheckCircle2 className="h-3 w-3" />
            <span>{result.short_id}</span>
          </div>
        )}
      </div>
    </div>
  );
}
