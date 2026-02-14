"use client";

import { Button } from "@/components/ui/button";
import { MultiSelect } from "@/components/ui/multi-select";
import { LayoutList, LayoutGrid } from "lucide-react";
import type { UsePageFiltersResult } from "@/lib/use-page-filters";

interface PageFiltersProps {
  filters: UsePageFiltersResult;
  /** Options for the type/status filter MultiSelect */
  typeOptions?: { value: string; label: string }[];
  typePlaceholder?: string;
  /** Extra controls to render after the standard filters */
  extra?: React.ReactNode;
}

/**
 * Standard toolbar filters for list pages.
 * Renders project MultiSelect + optional type MultiSelect + optional extras.
 */
export function PageFilters({
  filters,
  typeOptions,
  typePlaceholder = "All types",
  extra,
}: PageFiltersProps) {
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <MultiSelect
        options={filters.projectOptions}
        value={filters.projectFilter}
        onValueChange={filters.setProjectFilter}
        placeholder="All projects"
        searchPlaceholder="Search projects…"
        maxCount={2}
      />
      {typeOptions && (
        <MultiSelect
          options={typeOptions}
          value={filters.typeFilter}
          onValueChange={filters.setTypeFilter}
          placeholder={typePlaceholder}
          searchPlaceholder="Search…"
          maxCount={2}
        />
      )}
      {extra}
    </div>
  );
}

/**
 * Dense/card view toggle button. Pass as titleExtra to PageLayout.
 */
export function DenseToggle({
  dense,
  onToggle,
}: {
  dense: boolean;
  onToggle: () => void;
}) {
  return (
    <Button
      variant="ghost"
      size="sm"
      className="h-8 w-8 p-0"
      onClick={onToggle}
      title={dense ? "Card view" : "Dense view"}
    >
      {dense ? (
        <LayoutGrid className="h-4 w-4" />
      ) : (
        <LayoutList className="h-4 w-4" />
      )}
    </Button>
  );
}
