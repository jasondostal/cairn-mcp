"use client";

import { useEffect, useState } from "react";
import { api, type Project } from "@/lib/api";

interface UseProjectSelectorResult {
  projects: Project[];
  selected: string;
  setSelected: (name: string) => void;
  loading: boolean;
  error: string | null;
}

export function useProjectSelector(): UseProjectSelectorResult {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selected, setSelected] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    api
      .projects()
      .then((r) => {
        setProjects(r.items);
        if (r.items.length > 0) setSelected(r.items[0].name);
      })
      .catch((err) => setError(err?.message || "Failed to load projects"))
      .finally(() => setLoading(false));
  }, []);

  return { projects, selected, setSelected, loading, error };
}
