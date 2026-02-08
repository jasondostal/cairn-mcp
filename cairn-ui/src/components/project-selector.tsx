"use client";

import { Button } from "@/components/ui/button";
import type { Project } from "@/lib/api";

interface ProjectSelectorProps {
  projects: Project[];
  selected: string;
  onSelect: (name: string) => void;
}

export function ProjectSelector({
  projects,
  selected,
  onSelect,
}: ProjectSelectorProps) {
  return (
    <div className="flex gap-1 flex-wrap">
      {projects.map((p) => (
        <Button
          key={p.id}
          variant={selected === p.name ? "default" : "outline"}
          size="sm"
          onClick={() => onSelect(p.name)}
        >
          {p.name}
        </Button>
      ))}
    </div>
  );
}
