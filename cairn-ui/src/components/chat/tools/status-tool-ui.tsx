"use client";

import type { ToolCallMessagePartProps } from "@assistant-ui/react";
import { Activity, Loader2 } from "lucide-react";

interface StatusOutput {
  version: string;
  status: string;
  memories: number;
  projects: number;
  types: Record<string, number>;
}

export function StatusToolUI({
  result,
  status,
}: ToolCallMessagePartProps<Record<string, never>, StatusOutput>) {
  const isRunning = status.type === "running";

  return (
    <div className="my-1.5 rounded-md border border-border/50 bg-background/30 overflow-hidden">
      <div className="flex items-center gap-1.5 px-3 py-1.5 bg-muted/30">
        {isRunning ? (
          <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
        ) : (
          <Activity className="h-3 w-3 text-muted-foreground" />
        )}
        <span className="text-xs font-medium">system status</span>
        {result && (
          <span
            className={`ml-auto text-[10px] font-medium ${
              result.status === "healthy"
                ? "text-green-400"
                : "text-amber-400"
            }`}
          >
            {result.status}
          </span>
        )}
      </div>
      {result && (
        <div className="grid grid-cols-3 gap-2 px-3 py-2 text-xs">
          <div>
            <div className="text-[10px] text-muted-foreground">Version</div>
            <div className="font-mono text-foreground/80">
              v{result.version}
            </div>
          </div>
          <div>
            <div className="text-[10px] text-muted-foreground">Memories</div>
            <div className="font-mono text-foreground/80">
              {result.memories}
            </div>
          </div>
          <div>
            <div className="text-[10px] text-muted-foreground">Projects</div>
            <div className="font-mono text-foreground/80">
              {result.projects}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
