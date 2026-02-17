"use client";

import type { ToolCallMessagePartProps } from "@assistant-ui/react";
import { BookOpen, Loader2 } from "lucide-react";

interface MemoryDetail {
  id: number;
  content: string;
  summary: string | null;
  memory_type: string;
  project: string;
  importance: number;
  tags: string[];
}

interface RecallOutput {
  count: number;
  memories: MemoryDetail[];
}

type RecallArgs = { ids: number[] };

export function RecallToolUI({
  args,
  result,
  status,
}: ToolCallMessagePartProps<RecallArgs, RecallOutput>) {
  const isRunning = status.type === "running";

  return (
    <div className="my-1.5 rounded-md border border-border/50 bg-background/30 overflow-hidden">
      <div className="flex items-center gap-1.5 px-3 py-1.5 bg-muted/30 border-b border-border/30">
        <BookOpen className="h-3 w-3 text-muted-foreground" />
        <span className="text-xs font-medium">recall memory</span>
        <span className="text-xs text-muted-foreground">
          #{args.ids.join(", #")}
        </span>
        {isRunning && (
          <Loader2 className="ml-auto h-3 w-3 animate-spin text-muted-foreground" />
        )}
      </div>
      {result &&
        result.memories.map((m) => (
          <div key={m.id} className="px-3 py-2 border-b border-border/20 last:border-0">
            <div className="flex items-center gap-1.5 mb-1">
              <span className="font-mono text-[10px] text-muted-foreground">
                #{m.id}
              </span>
              <span className="rounded bg-muted px-1 py-0.5 text-[10px] font-medium">
                {m.memory_type}
              </span>
              <span className="text-[10px] text-muted-foreground">
                {m.project}
              </span>
              <span className="ml-auto text-[10px] text-muted-foreground">
                imp: {m.importance}
              </span>
            </div>
            <div className="text-xs text-foreground/80 whitespace-pre-wrap max-h-40 overflow-y-auto">
              {m.content.length > 500
                ? m.content.slice(0, 500) + "..."
                : m.content}
            </div>
          </div>
        ))}
    </div>
  );
}
