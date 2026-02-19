"use client";

import { useState } from "react";
import { api, type WorkItem, type WorkItemDetail, type WorkspaceBackendInfo } from "@/lib/api";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { SingleSelect } from "@/components/ui/single-select";
import { Bot, Loader2 } from "lucide-react";

interface DispatchDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  item: WorkItem | WorkItemDetail;
  backends: WorkspaceBackendInfo[];
  onDispatched?: () => void;
}

export function DispatchDialog({
  open,
  onOpenChange,
  item,
  backends,
  onDispatched,
}: DispatchDialogProps) {
  const [selectedBackend, setSelectedBackend] = useState("");
  const [selectedModel, setSelectedModel] = useState("");
  const [dispatching, setDispatching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const showBackendSelector = backends.length > 1;
  const showModelSelector = selectedBackend === "claude_code";

  async function handleDispatch() {
    setDispatching(true);
    setError(null);
    try {
      await api.workspaceCreateSession({
        project: item.project,
        work_item_id: item.id,
        backend: selectedBackend || undefined,
        model: selectedModel || undefined,
      });
      onDispatched?.();
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dispatch failed");
    } finally {
      setDispatching(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm" showCloseButton={false}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Bot className="h-4 w-4" />
            Dispatch to Agent
          </DialogTitle>
          <DialogDescription>
            <span className="font-mono">{item.short_id}</span> — {item.title}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          {showBackendSelector && (
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Backend
              </label>
              <SingleSelect
                options={[
                  { value: "", label: "Default" },
                  ...backends.map((b) => ({
                    value: b.name,
                    label: b.name === "claude_code" ? "Claude Code" : b.name === "opencode" ? "OpenCode" : b.name,
                  })),
                ]}
                value={selectedBackend}
                onValueChange={(v) => {
                  setSelectedBackend(v);
                  if (v !== "claude_code") setSelectedModel("");
                }}
                className="w-full"
              />
            </div>
          )}

          {showModelSelector && (
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Model
              </label>
              <SingleSelect
                options={[
                  { value: "", label: "Opus 4.6 (default)" },
                  { value: "claude-sonnet-4-6", label: "Sonnet 4.6 (faster)" },
                ]}
                value={selectedModel}
                onValueChange={setSelectedModel}
                className="w-full"
              />
            </div>
          )}

          {!showBackendSelector && (
            <p className="text-sm text-muted-foreground">
              The agent will receive the full work item briefing and begin working.
            </p>
          )}

          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)} disabled={dispatching}>
            Cancel
          </Button>
          <Button size="sm" onClick={handleDispatch} disabled={dispatching}>
            {dispatching ? (
              <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
            ) : (
              <Bot className="h-3.5 w-3.5 mr-1.5" />
            )}
            Dispatch
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
