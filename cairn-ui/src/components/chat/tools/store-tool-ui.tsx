"use client";

import type { ToolCallMessagePartProps } from "@assistant-ui/react";
import { Save, Loader2, CheckCircle2 } from "lucide-react";

interface StoreOutput {
  stored: boolean;
  id: number;
  project: string;
}

type StoreArgs = {
  content: string;
  project: string;
  memory_type?: string;
  importance?: number;
};

export function StoreToolUI({
  args,
  result,
  status,
}: ToolCallMessagePartProps<StoreArgs, StoreOutput>) {
  const isRunning = status.type === "running";

  return (
    <div className="my-1.5 rounded-md border border-border/50 bg-background/30 overflow-hidden">
      <div className="flex items-center gap-1.5 px-3 py-1.5 bg-muted/30">
        {isRunning ? (
          <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
        ) : (
          <Save className="h-3 w-3 text-muted-foreground" />
        )}
        <span className="text-xs font-medium">store memory</span>
        <span className="text-xs text-muted-foreground">
          in {args.project}
        </span>
        {result?.stored && (
          <div className="ml-auto flex items-center gap-1 text-[10px] text-green-400">
            <CheckCircle2 className="h-3 w-3" />
            <span>#{result.id}</span>
          </div>
        )}
      </div>
      {args.content && (
        <div className="px-3 py-1.5 text-xs text-foreground/70 border-t border-border/30">
          <div className="line-clamp-2">{args.content}</div>
          {args.memory_type && (
            <span className="mt-1 inline-block rounded bg-muted px-1 py-0.5 text-[10px]">
              {args.memory_type}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
