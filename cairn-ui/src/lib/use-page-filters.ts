"use client";

import { useEffect, useState, useCallback } from "react";
import { api, type Project } from "@/lib/api";

const STORAGE_KEY_PROJECTS = "cairn-filter-projects";
const STORAGE_KEY_DAYS = "cairn-filter-days";

function loadStoredProjects(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY_PROJECTS);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function loadStoredDays(): number | undefined {
  if (typeof window === "undefined") return undefined;
  try {
    const raw = localStorage.getItem(STORAGE_KEY_DAYS);
    if (!raw) return undefined;
    const n = Number(raw);
    return Number.isFinite(n) && n > 0 ? n : undefined;
  } catch {
    return undefined;
  }
}

/**
 * Standalone hook for pages that need shared days persistence
 * but don't use the full usePageFilters hook.
 */
export function useSharedDays(fallback = 7): [number, (v: number) => void] {
  const [days, setDaysState] = useState<number>(() => loadStoredDays() ?? fallback);
  const setDays = useCallback((v: number) => {
    setDaysState(v);
    try { localStorage.setItem(STORAGE_KEY_DAYS, String(v)); } catch { /* */ }
  }, []);
  return [days, setDays];
}

export interface UsePageFiltersOptions {
  /** Start in dense view (default: true) */
  defaultDense?: boolean;
  /** Default time range in days (undefined = no time filter managed by this hook) */
  defaultDays?: number;
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
  days: number | undefined;
  setDays: (v: number) => void;
}

export function usePageFilters(
  opts: UsePageFiltersOptions = {},
): UsePageFiltersResult {
  const { defaultDense = true, defaultDays } = opts;

  const [projects, setProjects] = useState<Project[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(true);
  const [projectFilter, setProjectFilterState] = useState<string[]>(loadStoredProjects);
  const [typeFilter, setTypeFilter] = useState<string[]>([]);
  const [dense, setDense] = useState(defaultDense);
  const [days, setDaysState] = useState<number | undefined>(
    () => loadStoredDays() ?? defaultDays,
  );

  useEffect(() => {
    api
      .projects()
      .then((r) => setProjects(r.items))
      .catch(() => {})
      .finally(() => setProjectsLoading(false));
  }, []);

  const setProjectFilter = useCallback((v: string[]) => {
    setProjectFilterState(v);
    try {
      if (v.length > 0) {
        localStorage.setItem(STORAGE_KEY_PROJECTS, JSON.stringify(v));
      } else {
        localStorage.removeItem(STORAGE_KEY_PROJECTS);
      }
    } catch { /* quota exceeded, etc */ }
  }, []);

  const setDays = useCallback((v: number) => {
    setDaysState(v);
    try {
      localStorage.setItem(STORAGE_KEY_DAYS, String(v));
    } catch { /* quota exceeded, etc */ }
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
    days,
    setDays,
  };
}
