"use client";

import { useEffect, useState } from "react";
import { api, type Project } from "@/lib/api";

export interface UsePageFiltersOptions {
  /** Start in dense view (default: true) */
  defaultDense?: boolean;
}

export interface UsePageFiltersResult {
  projects: Project[];
  projectFilter: string[];
  setProjectFilter: (v: string[]) => void;
  projectOptions: { value: string; label: string }[];
  projectsLoading: boolean;
  typeFilter: string[];
  setTypeFilter: (v: string[]) => void;
  dense: boolean;
  setDense: (v: boolean | ((prev: boolean) => boolean)) => void;
  showAllProjects: boolean;
}

export function usePageFilters(
  opts: UsePageFiltersOptions = {},
): UsePageFiltersResult {
  const { defaultDense = true } = opts;

  const [projects, setProjects] = useState<Project[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(true);
  const [projectFilter, setProjectFilter] = useState<string[]>([]);
  const [typeFilter, setTypeFilter] = useState<string[]>([]);
  const [dense, setDense] = useState(defaultDense);

  useEffect(() => {
    api
      .projects()
      .then((r) => setProjects(r.items))
      .catch(() => {})
      .finally(() => setProjectsLoading(false));
  }, []);

  const projectOptions = projects.map((p) => ({
    value: p.name,
    label: p.name,
  }));

  return {
    projects,
    projectFilter,
    setProjectFilter,
    projectOptions,
    projectsLoading,
    typeFilter,
    setTypeFilter,
    dense,
    setDense,
    showAllProjects: projectFilter.length === 0,
  };
}
