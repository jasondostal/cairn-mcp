import { cn } from "@/lib/utils";
import type { WorkItemStatus } from "@/lib/api";

const statusColors: Record<WorkItemStatus, string> = {
  open: "bg-status-open",
  ready: "bg-status-ready",
  in_progress: "bg-status-wip",
  blocked: "bg-status-blocked",
  done: "bg-status-done",
  cancelled: "bg-status-cancelled",
};

const statusTextColors: Record<WorkItemStatus, string> = {
  open: "text-status-open",
  ready: "text-status-ready",
  in_progress: "text-status-wip",
  blocked: "text-status-blocked",
  done: "text-status-done",
  cancelled: "text-status-cancelled line-through",
};

export function StatusDot({ status, className }: { status: WorkItemStatus; className?: string }) {
  return (
    <span
      role="status"
      aria-label={`Status: ${status.replace(/_/g, " ")}`}
      className={cn(
        "inline-block h-2 w-2 shrink-0 rounded-full",
        statusColors[status] ?? statusColors.open,
        status === "in_progress" && "animate-pulse",
        className,
      )}
    />
  );
}

export function StatusText({ status }: { status: WorkItemStatus }) {
  return (
    <span className={cn("text-xs font-mono", statusTextColors[status] ?? statusTextColors.open)}>
      {status}
    </span>
  );
}

export function PriorityDots({ priority }: { priority: number }) {
  const count = Math.min(Math.max(priority, 0), 5);
  if (count === 0) return null;
  return (
    <span className="inline-flex gap-px" title={`Priority ${priority}`} aria-label={`Priority ${priority} of 5`}>
      {Array.from({ length: count }, (_, i) => (
        <span key={i} className="inline-block h-1.5 w-1.5 rounded-full bg-muted-foreground" aria-hidden="true" />
      ))}
    </span>
  );
}

const priorityColors: Record<number, string> = {
  1: "text-muted-foreground",
  2: "text-status-ready",
  3: "text-status-wip",
  4: "text-priority-p4",
  5: "text-status-blocked",
};

export function PriorityLabel({ priority }: { priority: number }) {
  if (priority <= 0 || priority > 5) return null;
  return (
    <span
      className={cn("text-[10px] font-mono font-medium shrink-0", priorityColors[priority] ?? "text-muted-foreground")}
      title={`Priority ${priority}`}
    >
      P{priority}
    </span>
  );
}
