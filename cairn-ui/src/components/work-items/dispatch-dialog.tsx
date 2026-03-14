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
  const [selectedRiskTier, setSelectedRiskTier] = useState("");
  const [dispatching, setDispatching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const showBackendSelector = backends.length > 1;
  const showModelSelector = selectedBackend === "claude_code" || selectedBackend === "agent_sdk";
  const showRiskTier = selectedBackend === "agent_sdk";

  async function handleDispatch() {
    setDispatching(true);
    setError(null);
    try {
      await api.workspaceCreateSession({
        project: item.project,
        work_item_id: item.id,
        backend: selectedBackend || undefined,
        model: selectedModel || undefined,
        risk_tier: selectedRiskTier ? Number(selectedRiskTier) : undefined,
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
            <span className="font-mono">{item.display_id}</span> — {item.title}
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
                    label: b.name === "claude_code" ? "Claude Code"
                      : b.name === "opencode" ? "OpenCode"
                      : b.name === "agent_sdk" ? "Agent SDK"
                      : b.name,
                  })),
                ]}
                value={selectedBackend}
                onValueChange={(v) => {
                  setSelectedBackend(v);
                  if (v !== "claude_code" && v !== "agent_sdk") setSelectedModel("");
                  if (v !== "agent_sdk") setSelectedRiskTier("");
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

          {showRiskTier && (
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Risk Tier
              </label>
              <SingleSelect
                options={[
                  { value: "", label: "Default (Tier 1 — guided)" },
                  { value: "0", label: "Tier 0 — research only (read-only)" },
                  { value: "1", label: "Tier 1 — guided autonomy (edits auto-approved)" },
                  { value: "2", label: "Tier 2 — broad autonomy (edits + bash)" },
                  { value: "3", label: "Tier 3 — full autonomy (gated items only)" },
                ]}
                value={selectedRiskTier}
                onValueChange={setSelectedRiskTier}
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
