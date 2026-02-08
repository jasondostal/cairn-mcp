"use client";

import { useState } from "react";

export function useMemorySheet() {
  const [sheetId, setSheetId] = useState<number | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);

  function openSheet(id: number) {
    setSheetId(id);
    setSheetOpen(true);
  }

  return { sheetId, sheetOpen, setSheetOpen, openSheet };
}
