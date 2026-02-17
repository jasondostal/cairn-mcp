"use client";

import type { ToolCallMessagePartProps } from "@assistant-ui/react";
import { Search, Loader2 } from "lucide-react";

interface SearchResult {
  id: number;
  summary: string;
  memory_type: string;
  project: string;
  importance: number;
  tags: string[];
  score: number | null;
}

interface SearchOutput {
  count: number;
  results: SearchResult[];
}

type SearchArgs = { query: string; project?: string; limit?: number };

export function SearchToolUI({
  args,
  result,
  status,
}: ToolCallMessagePartProps<SearchArgs, SearchOutput>) {
  const isRunning = status.type === "running";

  return (
    <div className="my-1.5 rounded-md border border-border/50 bg-background/30 overflow-hidden">
      <div className="flex items-center gap-1.5 px-3 py-1.5 bg-muted/30 border-b border-border/30">
        <Search className="h-3 w-3 text-muted-foreground" />
        <span className="text-xs font-medium">search memories</span>
        <span className="text-xs text-muted-foreground truncate">
          &quot;{args.query}&quot;
        </span>
        {isRunning && (
          <Loader2 className="ml-auto h-3 w-3 animate-spin text-muted-foreground" />
        )}
        {result && (
          <span className="ml-auto text-[10px] text-muted-foreground">
            {result.count} result{result.count !== 1 ? "s" : ""}
          </span>
        )}
      </div>
      {result && result.results.length > 0 && (
        <div className="divide-y divide-border/30">
          {result.results.slice(0, 5).map((r) => (
            <div key={r.id} className="px-3 py-1.5 text-xs">
              <div className="flex items-center gap-1.5">
                <span className="font-mono text-[10px] text-muted-foreground">
                  #{r.id}
                </span>
                <span className="rounded bg-muted px-1 py-0.5 text-[10px] font-medium">
                  {r.memory_type}
                </span>
                <span className="text-[10px] text-muted-foreground">
                  {r.project}
                </span>
                {r.score != null && (
                  <span className="ml-auto text-[10px] text-muted-foreground">
                    {(r.score * 100).toFixed(0)}%
                  </span>
                )}
              </div>
              <div className="mt-0.5 text-foreground/80 line-clamp-2">
                {r.summary}
              </div>
              {r.tags.length > 0 && (
                <div className="mt-0.5 flex flex-wrap gap-1">
                  {r.tags.slice(0, 4).map((tag) => (
                    <span
                      key={tag}
                      className="rounded bg-primary/10 px-1 py-0.5 text-[9px] text-primary"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
          {result.count > 5 && (
            <div className="px-3 py-1 text-[10px] text-muted-foreground">
              +{result.count - 5} more
            </div>
          )}
        </div>
      )}
    </div>
  );
}
