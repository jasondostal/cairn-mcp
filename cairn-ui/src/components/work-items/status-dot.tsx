import { cn } from "@/lib/utils";
import type { WorkItemStatus } from "@/lib/api";

const statusColors: Record<WorkItemStatus, string> = {
  open: "bg-[oklch(0.556_0_0)]",
  ready: "bg-[oklch(0.488_0.243_264)]",
  in_progress: "bg-[oklch(0.769_0.188_70)]",
  blocked: "bg-[oklch(0.645_0.246_16)]",
  done: "bg-[oklch(0.696_0.17_162)]",
  cancelled: "bg-[oklch(0.556_0_0)]",
};

const statusTextColors: Record<WorkItemStatus, string> = {
  open: "text-[oklch(0.556_0_0)]",
  ready: "text-[oklch(0.488_0.243_264)]",
  in_progress: "text-[oklch(0.769_0.188_70)]",
  blocked: "text-[oklch(0.645_0.246_16)]",
  done: "text-[oklch(0.696_0.17_162)]",
  cancelled: "text-[oklch(0.556_0_0)] line-through",
};

export function StatusDot({ status, className }: { status: WorkItemStatus; className?: string }) {
  return (
    <span
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
    <span className="inline-flex gap-px" title={`Priority ${priority}`}>
      {Array.from({ length: count }, (_, i) => (
        <span key={i} className="inline-block h-1.5 w-1.5 rounded-full bg-muted-foreground/60" />
      ))}
    </span>
  );
}

const priorityColors: Record<number, string> = {
  1: "text-muted-foreground/70",
  2: "text-[oklch(0.488_0.243_264)]",
  3: "text-[oklch(0.769_0.188_70)]",
  4: "text-[oklch(0.705_0.213_47)]",
  5: "text-[oklch(0.645_0.246_16)]",
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
