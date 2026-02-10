"use client";

import { usePagination, PaginationControls } from "@/components/pagination";

interface PaginatedListProps<T> {
  items: T[];
  perPage?: number;
  noun: string;
  keyExtractor: (item: T) => string | number;
  renderItem: (item: T, index: number) => React.ReactNode;
  gap?: string;
}

export function PaginatedList<T>({
  items,
  perPage = 20,
  noun,
  keyExtractor,
  renderItem,
  gap = "space-y-3",
}: PaginatedListProps<T>) {
  const { page, totalPages, pageItems, setPage } = usePagination(items, perPage);

  return (
    <div className={gap}>
      <PaginationControls
        page={page}
        totalPages={totalPages}
        onPageChange={setPage}
        total={items.length}
        noun={noun}
      />
      {pageItems.map((item, i) => (
        <div key={keyExtractor(item)}>{renderItem(item, (page - 1) * perPage + i)}</div>
      ))}
      {totalPages > 1 && (
        <PaginationControls
          page={page}
          totalPages={totalPages}
          onPageChange={setPage}
          total={items.length}
          noun={noun}
        />
      )}
    </div>
  );
}
