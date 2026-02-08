"use client";

import { Skeleton } from "@/components/ui/skeleton";

export function SkeletonList({
  count = 4,
  height = "h-24",
  gap = "space-y-3",
}: {
  count?: number;
  height?: string;
  gap?: string;
}) {
  return (
    <div className={gap}>
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton key={i} className={height} />
      ))}
    </div>
  );
}
