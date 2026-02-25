"use client";

import { useState, useCallback } from "react";
import { useLocalStorage } from "@/lib/use-local-storage";
import {
  getDefaultLayouts,
  DEFAULT_VISIBLE_WIDGETS,
  WIDGET_MAP,
  type DashboardLayouts,
  type BreakpointLayout,
} from "@/lib/dashboard-registry";

// Bump this to force a layout reset when widget shape changes
const LAYOUT_VERSION = 1;
const LS_LAYOUTS = "cairn-dashboard-layouts";
const LS_VISIBLE = "cairn-dashboard-visible";
const LS_VERSION = "cairn-dashboard-layout-version";

export function useDashboardLayout() {
  const [version, setVersion] = useLocalStorage<number>(LS_VERSION, 0);
  const isStale = version !== LAYOUT_VERSION;

  const [layouts, setLayouts] = useLocalStorage<DashboardLayouts>(
    LS_LAYOUTS,
    getDefaultLayouts(),
  );
  const [visibleWidgets, setVisibleWidgets] = useLocalStorage<string[]>(
    LS_VISIBLE,
    DEFAULT_VISIBLE_WIDGETS,
  );
  const [isEditing, setEditing] = useState(false);

  // Force reset on version mismatch (runs once)
  if (isStale) {
    setLayouts(getDefaultLayouts());
    setVisibleWidgets(DEFAULT_VISIBLE_WIDGETS);
    setVersion(LAYOUT_VERSION);
  }

  const onLayoutChange = useCallback(
    (_current: BreakpointLayout, allLayouts: DashboardLayouts) => {
      setLayouts(allLayouts);
    },
    [setLayouts],
  );

  const addWidget = useCallback(
    (id: string) => {
      const def = WIDGET_MAP.get(id);
      if (!def) return;
      setVisibleWidgets((prev) => (prev.includes(id) ? prev : [...prev, id]));
      // Add default layout entries for new widget
      setLayouts((prev) => {
        const next: DashboardLayouts = {};
        for (const bp of ["lg", "md", "sm"] as const) {
          const existing = prev[bp] ?? [];
          if (existing.some((l) => l.i === id)) {
            next[bp] = existing;
          } else {
            next[bp] = [...existing, def.layouts[bp]];
          }
        }
        return next;
      });
    },
    [setVisibleWidgets, setLayouts],
  );

  const removeWidget = useCallback(
    (id: string) => {
      setVisibleWidgets((prev) => prev.filter((w) => w !== id));
    },
    [setVisibleWidgets],
  );

  const toggleWidget = useCallback(
    (id: string) => {
      if (visibleWidgets.includes(id)) {
        removeWidget(id);
      } else {
        addWidget(id);
      }
    },
    [visibleWidgets, removeWidget, addWidget],
  );

  const resetToDefaults = useCallback(() => {
    setLayouts(getDefaultLayouts());
    setVisibleWidgets(DEFAULT_VISIBLE_WIDGETS);
  }, [setLayouts, setVisibleWidgets]);

  return {
    layouts,
    visibleWidgets,
    isEditing,
    setEditing,
    onLayoutChange,
    addWidget,
    removeWidget,
    toggleWidget,
    resetToDefaults,
  };
}
