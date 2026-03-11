"use client";

import { Check, Plus } from "lucide-react";
import { WIDGET_REGISTRY } from "@/lib/dashboard-registry";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";

interface WidgetPickerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  visibleWidgets: string[];
  onToggle: (id: string) => void;
}

export function WidgetPicker({
  open,
  onOpenChange,
  visibleWidgets,
  onToggle,
}: WidgetPickerProps) {
  const visibleSet = new Set(visibleWidgets);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent>
        <SheetHeader>
          <SheetTitle>Widgets</SheetTitle>
          <SheetDescription>Toggle widgets on or off</SheetDescription>
        </SheetHeader>
        <div className="mt-4 space-y-1 overflow-y-auto max-h-[calc(100dvh-8rem)]">
          {WIDGET_REGISTRY.map((widget) => {
            const isVisible = visibleSet.has(widget.id);
            const Icon = widget.icon;
            return (
              <button
                key={widget.id}
                onClick={() => onToggle(widget.id)}
                className="flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left transition-colors hover:bg-accent"
              >
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-muted">
                  <Icon className="h-4 w-4 text-muted-foreground" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium">{widget.label}</div>
                  <div className="truncate text-xs text-muted-foreground">
                    {widget.description}
                  </div>
                </div>
                <div className="shrink-0">
                  {isVisible ? (
                    <Check className="h-4 w-4 text-primary" />
                  ) : (
                    <Plus className="h-4 w-4 text-muted-foreground" />
                  )}
                </div>
              </button>
            );
          })}
        </div>
      </SheetContent>
    </Sheet>
  );
}
