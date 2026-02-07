"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight } from "lucide-react";

interface UsePaginationResult<T> {
  page: number;
  totalPages: number;
  pageItems: T[];
  setPage: (p: number) => void;
}

export function usePagination<T>(
  items: T[],
  perPage: number = 20
): UsePaginationResult<T> {
  const [page, setPage] = useState(1);
  const prevLen = useRef(items.length);

  // Reset to page 1 when the dataset changes size (e.g. project switch)
  useEffect(() => {
    if (items.length !== prevLen.current) {
      setPage(1);
      prevLen.current = items.length;
    }
  }, [items.length]);

  const totalPages = Math.max(1, Math.ceil(items.length / perPage));
  const safePage = Math.min(page, totalPages);
  const start = (safePage - 1) * perPage;
  const pageItems = items.slice(start, start + perPage);

  return { page: safePage, totalPages, pageItems, setPage };
}

export function PaginationControls({
  page,
  totalPages,
  onPageChange,
  total,
  noun = "items",
}: {
  page: number;
  totalPages: number;
  onPageChange: (p: number) => void;
  total: number;
  noun?: string;
}) {
  if (totalPages <= 1) {
    return (
      <p className="text-sm text-muted-foreground">
        {total} {total === 1 ? noun.replace(/s$/, "") : noun}
      </p>
    );
  }

  return (
    <div className="flex items-center gap-3">
      <p className="text-sm text-muted-foreground">
        {total} {total === 1 ? noun.replace(/s$/, "") : noun}
      </p>
      <div className="flex items-center gap-1 ml-auto">
        <Button
          variant="outline"
          size="icon"
          className="h-8 w-8"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <span className="px-2 text-sm tabular-nums text-muted-foreground">
          {page} / {totalPages}
        </span>
        <Button
          variant="outline"
          size="icon"
          className="h-8 w-8"
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
