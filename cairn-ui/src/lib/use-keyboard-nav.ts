"use client";

import { useCallback, useEffect, useState } from "react";

/**
 * Keyboard navigation for lists: j/k to move, Enter to select, Esc to clear.
 *
 * Usage:
 *   const { activeIndex, handlers } = useKeyboardNav({
 *     itemCount: items.length,
 *     onSelect: (index) => openSheet(items[index].id),
 *   });
 *
 *   <div {...handlers}> ... items.map((item, i) => <div data-active={i === activeIndex} />) </div>
 */
export function useKeyboardNav({
  itemCount,
  onSelect,
  enabled = true,
}: {
  itemCount: number;
  onSelect?: (index: number) => void;
  enabled?: boolean;
}) {
  const [activeIndex, setActiveIndex] = useState(-1);

  // Reset when item count changes
  useEffect(() => {
    setActiveIndex(-1);
  }, [itemCount]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!enabled || itemCount === 0) return;

      // Don't hijack keyboard when typing in inputs
      const target = e.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT") return;

      // Don't interfere with Cmd+K or other meta combos
      if (e.metaKey || e.ctrlKey || e.altKey) return;

      switch (e.key) {
        case "j":
        case "ArrowDown":
          e.preventDefault();
          setActiveIndex((i) => Math.min(i + 1, itemCount - 1));
          break;
        case "k":
        case "ArrowUp":
          e.preventDefault();
          setActiveIndex((i) => Math.max(i - 1, 0));
          break;
        case "Enter":
          if (activeIndex >= 0 && onSelect) {
            e.preventDefault();
            onSelect(activeIndex);
          }
          break;
        case "Escape":
          setActiveIndex(-1);
          break;
      }
    },
    [enabled, itemCount, activeIndex, onSelect],
  );

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  return { activeIndex, setActiveIndex };
}
