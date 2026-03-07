"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { Project } from "@/lib/api";
import { EntityCreateDialog } from "./entity-create-dialog";
import { type GraphMode, ENTITY_TYPES, RELATION_TYPES } from "./graph-types";

// ────────────────────────────────────────────────────
// Props
// ────────────────────────────────────────────────────

interface GraphFiltersProps {
  mode: GraphMode;
  // Neo4j filters
  searchTerm: string;
  onSearchTermChange: (term: string) => void;
  entityTypeFilter: string;
  onEntityTypeFilterChange: (type: string) => void;
  // Postgres filters
  relationType: string;
  onRelationTypeChange: (type: string) => void;
  colorMode: "type" | "cluster";
  onColorModeChange: (mode: "type" | "cluster") => void;
  // Entity creation
  projects: Project[];
  defaultProject?: string;
  onEntityCreated: () => void;
}

// ────────────────────────────────────────────────────
// Component
// ────────────────────────────────────────────────────

export function GraphFilters({
  mode,
  searchTerm,
  onSearchTermChange,
  entityTypeFilter,
  onEntityTypeFilterChange,
  relationType,
  onRelationTypeChange,
  colorMode,
  onColorModeChange,
  projects,
  defaultProject,
  onEntityCreated,
}: GraphFiltersProps) {
  return (
    <>
      {/* Neo4j: entity search (client-side highlight, no reload) */}
      {mode === "neo4j" && (
        <Input
          placeholder="Search entities..."
          value={searchTerm}
          onChange={(e) => onSearchTermChange(e.target.value)}
          className="w-48"
        />
      )}

      {/* Neo4j: create entity */}
      {mode === "neo4j" && (
        <EntityCreateDialog
          projects={projects}
          defaultProject={defaultProject}
          onCreated={onEntityCreated}
        />
      )}

      {/* Neo4j: entity type buttons */}
      {mode === "neo4j" && (
        <div className="flex gap-1 overflow-x-auto">
          {ENTITY_TYPES.map((et) => (
            <Button
              key={et}
              variant={entityTypeFilter === et ? "default" : "outline"}
              size="sm"
              onClick={() => onEntityTypeFilterChange(et)}
              className="whitespace-nowrap"
            >
              {et === "all" ? "All" : et}
            </Button>
          ))}
        </div>
      )}

      {/* Postgres: relation type buttons */}
      {mode === "postgres" && (
        <div className="flex gap-1">
          {RELATION_TYPES.map((rt) => (
            <Button
              key={rt}
              variant={relationType === rt ? "default" : "outline"}
              size="sm"
              onClick={() => onRelationTypeChange(rt)}
            >
              {rt === "all" ? "All" : rt.replace("_", " ")}
            </Button>
          ))}
        </div>
      )}

      {/* Postgres: color mode toggle */}
      {mode === "postgres" && (
        <Button
          variant={colorMode === "cluster" ? "default" : "outline"}
          size="sm"
          onClick={() => onColorModeChange(colorMode === "cluster" ? "type" : "cluster")}
        >
          {colorMode === "cluster" ? "Color: Cluster" : "Color: Type"}
        </Button>
      )}
    </>
  );
}
