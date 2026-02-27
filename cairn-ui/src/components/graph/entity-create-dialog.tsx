"use client";

import { useState } from "react";
import { api, type Project } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { SingleSelect } from "@/components/ui/single-select";
import { Plus, Loader2 } from "lucide-react";

const ENTITY_TYPES = [
  "Person",
  "Organization",
  "Place",
  "Event",
  "Project",
  "Task",
  "Technology",
  "Product",
  "Concept",
];

interface EntityCreateDialogProps {
  projects: Project[];
  defaultProject?: string;
  onCreated: () => void;
}

export function EntityCreateDialog({ projects, defaultProject, onCreated }: EntityCreateDialogProps) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [entityType, setEntityType] = useState("Concept");
  const [project, setProject] = useState(defaultProject || "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!name.trim() || !project) return;
    setSaving(true);
    setError(null);
    try {
      await api.createEntity({
        name: name.trim(),
        entity_type: entityType,
        project,
      });
      setOpen(false);
      setName("");
      setEntityType("Concept");
      onCreated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create entity");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <Plus className="mr-1 h-3 w-3" />
          Entity
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Create Entity</DialogTitle>
          <DialogDescription>
            Add a new entity to the knowledge graph.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-2">
          <div>
            <label className="text-xs font-medium text-muted-foreground">Name</label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Alice, Cairn, React..."
              className="mt-1"
              autoFocus
              onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
            />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Type</label>
            <div className="mt-1">
              <SingleSelect
                options={ENTITY_TYPES.map((t) => ({ value: t, label: t }))}
                value={entityType}
                onValueChange={setEntityType}
              />
            </div>
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Project</label>
            <div className="mt-1">
              <SingleSelect
                options={projects.map((p) => ({ value: p.name, label: p.name }))}
                value={project}
                onValueChange={setProject}
                placeholder="Select project"
              />
            </div>
          </div>
          {error && (
            <p className="text-xs text-destructive">{error}</p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
          <Button onClick={handleSubmit} disabled={saving || !name.trim() || !project}>
            {saving && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}
            Create
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
