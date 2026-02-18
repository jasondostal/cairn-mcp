"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Download } from "lucide-react";

interface DownloadOption {
  label: string;
  onClick: () => void;
}

export function DownloadMenu({ options }: { options: DownloadOption[] }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="relative">
      <Button variant="outline" size="sm" onClick={() => setOpen(!open)}>
        <Download className="mr-1.5 h-4 w-4" />
        Download
      </Button>
      {open && (
        <div className="absolute right-0 top-full z-10 mt-1 rounded-md border border-border bg-popover p-1 shadow-md">
          {options.map((opt) => (
            <button
              key={opt.label}
              onClick={() => {
                setOpen(false);
                opt.onClick();
              }}
              className="block w-full rounded-sm px-3 py-1.5 text-left text-sm whitespace-nowrap hover:bg-accent hover:text-accent-foreground"
            >
              {opt.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
