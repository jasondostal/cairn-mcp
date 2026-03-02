"use client";

import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";

export interface TimePreset {
  label: string;
  value: number;
}

export const DEFAULT_TIME_PRESETS: TimePreset[] = [
  { label: "7d", value: 7 },
  { label: "30d", value: 30 },
  { label: "90d", value: 90 },
];

/** OKLCH accent for the active segment */
const ACTIVE_COLOR = "oklch(0.72 0.19 165)";

interface TimeRangeFilterProps {
  days: number;
  onChange: (days: number) => void;
  presets?: TimePreset[];
}

export function TimeRangeFilter({
  days,
  onChange,
  presets = DEFAULT_TIME_PRESETS,
}: TimeRangeFilterProps) {
  return (
    <ToggleGroup
      type="single"
      variant="outline"
      size="sm"
      value={String(days)}
      onValueChange={(v) => { if (v) onChange(Number(v)); }}
    >
      {presets.map((p) => (
        <ToggleGroupItem
          key={p.value}
          value={String(p.value)}
          className="text-xs px-2.5 data-[state=on]:text-foreground"
          style={
            days === p.value
              ? {
                  backgroundColor: `color-mix(in oklch, ${ACTIVE_COLOR} 15%, transparent)`,
                  borderColor: `color-mix(in oklch, ${ACTIVE_COLOR} 40%, transparent)`,
                  color: ACTIVE_COLOR,
                }
              : undefined
          }
        >
          {p.label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}
