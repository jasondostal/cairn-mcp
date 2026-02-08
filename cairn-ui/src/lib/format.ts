/**
 * Shared date formatting utilities for the Cairn UI.
 *
 * Each function preserves the exact output of the inline formatting it replaces.
 */

/**
 * Format a date string using the browser default locale date format.
 *
 * Equivalent to: `new Date(value).toLocaleDateString()`
 *
 * Used in: search, tasks, thinking, projects, clusters, rules, memories, thinking detail.
 */
export function formatDate(value: string): string {
  return new Date(value).toLocaleDateString();
}

/**
 * Format a time string as HH:MM (2-digit hour and minute).
 *
 * Equivalent to: `new Date(value).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })`
 *
 * Used in: timeline cards.
 */
export function formatTime(value: string): string {
  return new Date(value).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Format a time string using the browser default locale time format.
 *
 * Equivalent to: `new Date(value).toLocaleTimeString()`
 *
 * Used in: thinking detail thought cards.
 */
export function formatTimeFull(value: string): string {
  return new Date(value).toLocaleTimeString();
}

/**
 * Format a date string using the browser default locale date and time format.
 *
 * Equivalent to: `new Date(value).toLocaleString()`
 *
 * Used in: memory-sheet (created_at, updated_at displays).
 */
export function formatDateTime(value: string): string {
  return new Date(value).toLocaleString();
}

/**
 * Format a date string with weekday, abbreviated month, and day.
 *
 * Equivalent to: `date.toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" })`
 *
 * Used in: timeline groupByDate for non-today/yesterday labels.
 */
export function formatDateLong(value: string): string {
  return new Date(value).toLocaleDateString(undefined, {
    weekday: "long",
    month: "short",
    day: "numeric",
  });
}

/**
 * Compute a relative date label: "Today", "Yesterday", or a long-form date.
 *
 * This replicates the groupByDate labelling logic from the timeline page.
 * The date parameter should already have hours zeroed out for comparison,
 * but this function handles that internally for convenience.
 */
export function formatRelativeDate(value: string): string {
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);

  const date = new Date(value);
  date.setHours(0, 0, 0, 0);

  if (date.getTime() === today.getTime()) {
    return "Today";
  }
  if (date.getTime() === yesterday.getTime()) {
    return "Yesterday";
  }
  return date.toLocaleDateString(undefined, {
    weekday: "long",
    month: "short",
    day: "numeric",
  });
}
