"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SingleSelect } from "@/components/ui/single-select";

interface CreateWorkItemDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projects: { value: string; label: string }[];
  defaultProject?: string;
  onCreated?: () => void;
}

export function CreateWorkItemDialog({
  open,
  onOpenChange,
  projects,
  defaultProject,
  onCreated,
}: CreateWorkItemDialogProps) {
  const [project, setProject] = useState(defaultProject || "");
  const [title, setTitle] = useState("");
  const [itemType, setItemType] = useState("task");
  const [priority, setPriority] = useState(0);
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset form when dialog opens
  function handleOpenChange(v: boolean) {
    if (v) {
      setProject(defaultProject || "");
      setTitle("");
      setItemType("task");
      setPriority(0);
      setDescription("");
      setError(null);
    }
    onOpenChange(v);
  }

  async function handleCreate() {
    if (!project || !title.trim()) return;
    setCreating(true);
    setError(null);
    try {
      await api.workItemCreate({
        project,
        title: title.trim(),
        item_type: itemType,
        priority,
        description: description.trim() || undefined,
      });
      onCreated?.();
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create work item");
    } finally {
      setCreating(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>New Work Item</DialogTitle>
          <DialogDescription>Create a new epic, task, or subtask.</DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-2">
          {/* Project */}
          <div className="space-y-1">
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Project
            </span>
            <SingleSelect
              options={projects}
              value={project}
              onValueChange={setProject}
              placeholder="Select project…"
              className="w-full h-8"
            />
          </div>

          {/* Title */}
          <div className="space-y-1">
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Title
            </span>
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Work item title…"
              className="h-8"
              autoFocus
              onKeyDown={(e) => {
                if (e.key === "Enter" && project && title.trim()) {
                  handleCreate();
                }
              }}
            />
          </div>

          {/* Type + Priority row */}
          <div className="flex gap-3">
            <div className="space-y-1 flex-1">
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Type
              </span>
              <SingleSelect
                options={[
                  { value: "epic", label: "epic" },
                  { value: "task", label: "task" },
                  { value: "subtask", label: "subtask" },
                ]}
                value={itemType}
                onValueChange={setItemType}
                className="w-full h-8"
              />
            </div>
            <div className="space-y-1 w-24">
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Priority
              </span>
              <Input
                type="number"
                min={0}
                max={10}
                value={priority}
                onChange={(e) => setPriority(Number(e.target.value))}
                className="h-8"
              />
            </div>
          </div>

          {/* Description */}
          <div className="space-y-1">
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Description
            </span>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional description…"
              rows={3}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 resize-none"
            />
          </div>

          {error && (
            <p className="text-xs text-destructive">{error}</p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            size="sm"
            onClick={handleCreate}
            disabled={creating || !project || !title.trim()}
          >
            {creating ? "Creating…" : "Create"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
